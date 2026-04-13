#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import socket
import ssl
import statistics
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field, is_dataclass
from http.cookiejar import CookieJar
from typing import Any


DEFAULT_TIMEOUT = 5.0
SNMP_SYS_DESCR_GET = bytes.fromhex(
    "302602010004067075626c6963a019020101020100020100300e300c06082b060102010101000500"
)


@dataclass
class CheckResult:
    name: str
    status: str
    proof: str
    detail: str
    latency_ms: float | None = None
    evidence: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


def url_for(host: str, port: int, scheme: str, path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{scheme}://{host}:{port}{normalized}"


def make_cookie_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def http_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    opener: urllib.request.OpenerDirector | None = None,
    verify_tls: bool = True,
) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(url, method=method, data=data)
    for key, value in (headers or {}).items():
        req.add_header(key, value)

    try:
        if urllib.parse.urlparse(url).scheme == "https" and not verify_tls and opener is None:
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
                return response.getcode(), response.read(), dict(response.headers.items())

        client = opener or urllib.request.build_opener()
        with client.open(req, timeout=timeout) as response:
            return response.getcode(), response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())


def multipart_form_data(
    fields: dict[str, str],
    files: list[tuple[str, str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f"----koth-qa-{int(time.time() * 1000)}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )
    for field_name, filename, content, content_type in files:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{field_name}"; '
                    f'filename="{filename}"\r\n'
                ).encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def tcp_roundtrip(
    host: str,
    port: int,
    *,
    send: bytes = b"",
    timeout: float = DEFAULT_TIMEOUT,
    recv_bytes: int = 4096,
) -> tuple[float, bytes]:
    started = time.perf_counter()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        if send:
            sock.sendall(send)
        data = sock.recv(recv_bytes) if recv_bytes else b""
    return (time.perf_counter() - started) * 1000.0, data


def udp_roundtrip(
    host: str,
    port: int,
    payload: bytes,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    recv_bytes: int = 4096,
) -> tuple[float, bytes]:
    started = time.perf_counter()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(payload, (host, port))
        data, _ = sock.recvfrom(recv_bytes)
    return (time.perf_counter() - started) * 1000.0, data


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def run_command(command: list[str], *, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize_latencies(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}
    return {
        "mean_ms": round(statistics.fmean(samples), 2),
        "p50_ms": round(percentile(samples, 0.50), 2),
        "p95_ms": round(percentile(samples, 0.95), 2),
        "p99_ms": round(percentile(samples, 0.99), 2),
    }


def result_to_dict(result: Any) -> Any:
    if is_dataclass(result):
        return asdict(result)
    if isinstance(result, dict):
        return {key: result_to_dict(value) for key, value in result.items()}
    if isinstance(result, list):
        return [result_to_dict(item) for item in result]
    return result


def write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(result_to_dict(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def render(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(cells))

    print(render(headers))
    print(render(["-" * width for width in widths]))
    for row in rows:
        print(render(row))
