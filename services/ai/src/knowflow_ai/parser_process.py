"""Bound parser work in a killable child process."""
import asyncio
import json
import os
import signal
import sys

from .parsing import ParseFailure, ParseLimits, ParsedDocument, TextBlock

PARSER_TIMEOUT_SECONDS = 15.0
PARSER_MEMORY_LIMIT_BYTES = 512 * 1024 * 1024
MAX_PARSER_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_PARSER_INPUT_BYTES = 8 * 1024 * 1024


async def _stop(process, communication):
    if process.returncode is None:
        _kill(process)
    await asyncio.gather(communication, return_exceptions=True)
    await process.wait()


def _kill(process):
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass


async def _write_request(process, request):
    process.stdin.write(request)
    try:
        await process.stdin.drain()
    except (BrokenPipeError, ConnectionResetError):
        pass
    process.stdin.close()


async def _communicate_bounded(process, request):
    writer = asyncio.create_task(_write_request(process, request))
    output = bytearray()
    try:
        while chunk := await process.stdout.read(64 * 1024):
            if len(output) + len(chunk) > MAX_PARSER_OUTPUT_BYTES:
                _kill(process)
                while await process.stdout.read(64 * 1024):
                    pass
                await process.wait()
                await writer
                raise ParseFailure("PARSER_RESOURCE_LIMIT")
            output.extend(chunk)
        await writer
        await process.wait()
        return bytes(output)
    except BaseException:
        if process.returncode is None:
            _kill(process)
        try:
            while await process.stdout.read(64 * 1024):
                pass
        except (BrokenPipeError, ConnectionResetError):
            pass
        await process.wait()
        await asyncio.gather(writer, return_exceptions=True)
        raise


async def parse_document_isolated(data: bytes, *, format: str, document_id: str,
                                  content_version_id: str, file_id: str,
                                  limits: ParseLimits | None = None,
                                  enable_ocr: bool = True,
                                  timeout_seconds: float = PARSER_TIMEOUT_SECONDS) -> ParsedDocument:
    limits = limits or ParseLimits()
    if not isinstance(data, bytes):
        raise ParseFailure("INVALID_INPUT_TYPE")
    if len(data) > min(limits.max_file_bytes, MAX_PARSER_INPUT_BYTES):
        raise ParseFailure("FILE_TOO_LARGE")
    metadata = {
        "data_length": len(data),
        "format": format,
        "document_id": document_id,
        "content_version_id": content_version_id,
        "file_id": file_id,
        "enable_ocr": enable_ocr,
        "limits": {"max_file_bytes": limits.max_file_bytes,
                   "max_pdf_pages": limits.max_pdf_pages,
                   "max_characters": limits.max_characters},
    }
    request = json.dumps(metadata, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    if isinstance(data, bytes):
        request += data
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-I", "-m", "knowflow_ai.parser_worker",
            str(PARSER_MEMORY_LIMIT_BYTES), str(MAX_PARSER_INPUT_BYTES),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, start_new_session=os.name == "posix")
    except OSError:
        raise ParseFailure("PARSER_UNAVAILABLE") from None

    communication = asyncio.create_task(_communicate_bounded(process, request))
    try:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError
        stdout = await asyncio.wait_for(asyncio.shield(communication), remaining)
    except TimeoutError:
        await asyncio.shield(asyncio.create_task(_stop(process, communication)))
        raise ParseFailure("PARSER_TIMEOUT") from None
    except asyncio.CancelledError:
        await asyncio.shield(asyncio.create_task(_stop(process, communication)))
        raise
    if process.returncode != 0:
        raise ParseFailure("PARSER_RESOURCE_LIMIT")
    try:
        result = json.loads(stdout)
        if set(result) == {"error"} and isinstance(result["error"], str):
            raise ParseFailure(result["error"])
        if set(result) != {"document"}:
            raise ValueError
        document = result["document"]
        blocks = tuple(TextBlock(**item) for item in document.pop("blocks"))
        document["empty_pages"] = tuple(document["empty_pages"])
        return ParsedDocument(**document, blocks=blocks)
    except ParseFailure:
        raise
    except (ValueError, TypeError, KeyError, UnicodeDecodeError):
        raise ParseFailure("PARSER_FAILURE") from None
