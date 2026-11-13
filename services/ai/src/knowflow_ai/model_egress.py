"""CONNECT-only egress for user-supplied HTTPS model endpoints."""
import asyncio
import ipaddress
import os
import re
import socket

_TARGET = re.compile(rb"CONNECT ([a-zA-Z0-9.-]{1,253}):443 HTTP/1\.[01]")
_DOMAIN = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,62}", re.ASCII)
_BLOCKED_RANGES = tuple(ipaddress.ip_network(cidr) for cidr in (
    "168.63.129.16/32", "192.0.0.0/24", "192.88.99.0/24",
    "::ffff:0:0/96", "64:ff9b::/96", "64:ff9b:1::/48", "2001::/32", "2002::/16",
))


def allowed_address(address, denied=()):
    ip = ipaddress.ip_address(address)
    return (ip.is_global and not ip.is_multicast and not ip.is_reserved
            and not any(ip in network for network in (*_BLOCKED_RANGES, *denied)))


async def resolve_public(host, denied):
    if not _DOMAIN.fullmatch(host):
        raise ValueError("Invalid destination")
    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(host + ".", 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    addresses = list(dict.fromkeys((record[0], record[4][0]) for record in records))
    if not addresses or not all(allowed_address(ip, denied) for _, ip in addresses):
        raise ValueError("Blocked destination")
    return addresses


async def connect_public(host, denied):
    for family, address in await resolve_public(host, denied):
        try:
            async with asyncio.timeout(2):
                return await asyncio.open_connection(address, 443, family=family, flags=socket.AI_NUMERICHOST)
        except (OSError, TimeoutError):
            continue
    raise OSError("Destination unavailable")


async def _pipe(reader, writer):
    while chunk := await reader.read(32 * 1024):
        writer.write(chunk)
        await writer.drain()
    if writer.can_write_eof():
        writer.write_eof()


async def tunnel(reader, writer, denied):
    upstream_writer = None
    try:
        try:
            async with asyncio.timeout(6):
                headers = await reader.readuntil(b"\r\n\r\n")
                target = _TARGET.fullmatch(headers.split(b"\r\n", 1)[0])
                if target is None:
                    raise ValueError("Invalid target")
                upstream_reader, upstream_writer = await connect_public(target[1].decode().lower(), denied)
        except (ValueError, OSError, TimeoutError, asyncio.LimitOverrunError, asyncio.IncompleteReadError):
            writer.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            return
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        async with asyncio.timeout(45):
            async with asyncio.TaskGroup() as pipes:
                pipes.create_task(_pipe(reader, upstream_writer))
                pipes.create_task(_pipe(upstream_reader, writer))
    except* (OSError, TimeoutError):
        pass
    finally:
        writer.close()
        if upstream_writer is not None:
            upstream_writer.close()


async def serve():
    denied = tuple(ipaddress.ip_network(cidr.strip()) for cidr in
                   os.environ.get("KNOWFLOW_CUSTOM_LLM_DENY_CIDRS", "").split(",") if cidr.strip())
    active = 0

    async def accept(reader, writer):
        nonlocal active
        if active >= 32:
            writer.close()
            return
        active += 1
        try:
            await tunnel(reader, writer, denied)
        finally:
            active -= 1

    async with await asyncio.start_server(accept, "0.0.0.0", 3129, limit=8192) as server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(serve())
