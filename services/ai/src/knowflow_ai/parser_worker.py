"""Child entry point: install an OS memory limit before importing the parser."""
import ctypes
import json
import os
import sys

_job_handle = None


def _apply_windows_memory_limit(limit_bytes):
    from ctypes import wintypes

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.argtypes = ()
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise RuntimeError("PARSER_MEMORY_LIMIT_UNAVAILABLE")
    info = ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.ProcessMemoryLimit = limit_bytes
    if not kernel32.SetInformationJobObject(
            job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        raise RuntimeError("PARSER_MEMORY_LIMIT_UNAVAILABLE")
    if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
        raise RuntimeError("PARSER_MEMORY_LIMIT_UNAVAILABLE")
    global _job_handle
    _job_handle = job


def _apply_memory_limit(limit_bytes):
    if type(limit_bytes) is not int or limit_bytes < 1:
        raise RuntimeError("PARSER_MEMORY_LIMIT_UNAVAILABLE")
    if os.name == "nt":
        _apply_windows_memory_limit(limit_bytes)
        return
    try:
        import resource

        infinity = resource.RLIM_INFINITY
        _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        limit = limit_bytes if hard == infinity else min(limit_bytes, hard)
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, OSError, ValueError):
        raise RuntimeError("PARSER_MEMORY_LIMIT_UNAVAILABLE") from None


def _error(code):
    sys.stdout.buffer.write(json.dumps({"error": code}, separators=(",", ":")).encode("ascii"))
    sys.stdout.buffer.flush()


def main():
    try:
        if len(sys.argv) != 3:
            raise ValueError
        _apply_memory_limit(int(sys.argv[1]))
        max_input_bytes = int(sys.argv[2])
        if max_input_bytes < 1:
            raise ValueError
    except Exception:
        _error("PARSER_RESOURCE_LIMIT_UNAVAILABLE")
        return 0

    try:
        header = sys.stdin.buffer.readline(4097)
        if len(header) > 4096 or not header.endswith(b"\n"):
            raise ValueError
        metadata = json.loads(header)
        expected = {"data_length", "format", "document_id", "content_version_id", "file_id", "limits"}
        if set(metadata) != expected or type(metadata["data_length"]) is not int:
            raise ValueError
        if not 0 <= metadata["data_length"] <= max_input_bytes:
            raise ValueError
        data = sys.stdin.buffer.read(metadata["data_length"])
        if len(data) != metadata["data_length"] or sys.stdin.buffer.read(1):
            raise ValueError
        limits = metadata["limits"]
        if (not isinstance(limits, dict)
                or set(limits) != {"max_file_bytes", "max_pdf_pages", "max_characters"}):
            raise ValueError
    except (ValueError, TypeError, KeyError, UnicodeDecodeError):
        _error("PARSER_FAILURE")
        return 0

    try:
        from .parsing import ParseFailure, ParseLimits, parse_document

        parsed = parse_document(
            data, format=metadata["format"], document_id=metadata["document_id"],
            content_version_id=metadata["content_version_id"], file_id=metadata["file_id"],
            limits=ParseLimits(**limits))
        document = {
            "document_id": parsed.document_id,
            "content_version_id": parsed.content_version_id,
            "file_id": parsed.file_id,
            "file_sha256": parsed.file_sha256,
            "format": parsed.format,
            "blocks": [{"sequence": block.sequence, "text": block.text,
                        "page": block.page, "char_start": block.char_start,
                        "char_end": block.char_end} for block in parsed.blocks],
            "characters": parsed.characters,
            "pages": parsed.pages,
            "empty_pages": parsed.empty_pages,
            "parser_profile": parsed.parser_profile,
        }
        output = {"document": document}
    except ParseFailure as error:
        output = {"error": str(error)}
    except MemoryError:
        output = {"error": "PARSER_MEMORY_LIMIT"}
    except Exception:
        output = {"error": "PARSER_FAILURE"}
    sys.stdout.buffer.write(json.dumps(output, ensure_ascii=False, separators=(",", ":"),
                                      allow_nan=False).encode("utf-8"))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
