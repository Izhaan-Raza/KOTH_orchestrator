#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import time
from dataclasses import dataclass

from common import (
    SNMP_SYS_DESCR_GET,
    http_request,
    print_table,
    summarize_latencies,
    tcp_roundtrip,
    udp_roundtrip,
    url_for,
    write_json,
)
from targets import Target, selected_targets


@dataclass
class ProbeOutcome:
    ok: bool
    latency_ms: float
    detail: str


def http_probe(host: str, target: Target, timeout: float) -> ProbeOutcome:
    url = url_for(host, target.port, target.load_protocol, target.load_path or "/")
    started = time.perf_counter()
    status, body, _ = http_request(url, timeout=timeout, verify_tls=False)
    latency_ms = (time.perf_counter() - started) * 1000.0
    ok = 200 <= status < 500 and len(body) >= 0
    return ProbeOutcome(ok, latency_ms, f"status={status}")


def tcp_probe(host: str, target: Target, timeout: float) -> ProbeOutcome:
    latency_ms, body = tcp_roundtrip(host, target.port, timeout=timeout, recv_bytes=0)
    return ProbeOutcome(True, latency_ms, f"bytes={len(body)}")


def redis_probe(host: str, target: Target, timeout: float) -> ProbeOutcome:
    ping = b"*1\r\n$4\r\nPING\r\n"
    latency_ms, body = tcp_roundtrip(host, target.port, send=ping, timeout=timeout)
    ok = b"PONG" in body
    return ProbeOutcome(ok, latency_ms, body.decode(errors="ignore").strip() or "empty response")


def rsync_probe(host: str, target: Target, timeout: float) -> ProbeOutcome:
    latency_ms, body = tcp_roundtrip(host, target.port, timeout=timeout)
    text = body.decode(errors="ignore").strip()
    return ProbeOutcome("@RSYNCD:" in text, latency_ms, text or "empty banner")


def udp_snmp_probe(host: str, target: Target, timeout: float) -> ProbeOutcome:
    latency_ms, body = udp_roundtrip(host, target.port, SNMP_SYS_DESCR_GET, timeout=timeout)
    return ProbeOutcome(len(body) > 0 and body[:1] == b"\x30", latency_ms, f"bytes={len(body)}")


def run_probe(host: str, target: Target, timeout: float) -> ProbeOutcome:
    if target.load_protocol in {"http", "https"}:
        return http_probe(host, target, timeout)
    if target.load_protocol == "redis":
        return redis_probe(host, target, timeout)
    if target.load_protocol == "rsync":
        return rsync_probe(host, target, timeout)
    if target.load_protocol == "udp_snmp":
        return udp_snmp_probe(host, target, timeout)
    return tcp_probe(host, target, timeout)


def run_target(host: str, target: Target, requests: int, concurrency: int, timeout: float) -> dict[str, object]:
    outcomes: list[ProbeOutcome] = []
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(run_probe, host, target, timeout) for _ in range(requests)]
        for future in concurrent.futures.as_completed(futures):
            outcomes.append(future.result())

    duration = time.perf_counter() - started
    latencies = [item.latency_ms for item in outcomes if item.ok]
    successes = sum(1 for item in outcomes if item.ok)
    failures = len(outcomes) - successes
    sample_detail = next((item.detail for item in outcomes if item.detail), "")

    return {
        "target": target.name,
        "protocol": target.load_protocol,
        "requests": requests,
        "concurrency": concurrency,
        "successes": successes,
        "failures": failures,
        "success_rate": round((successes / requests) * 100.0, 2) if requests else 0.0,
        "throughput_rps": round(requests / duration, 2) if duration else 0.0,
        "duration_s": round(duration, 2),
        "latency": summarize_latencies(latencies),
        "sample_detail": sample_detail,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Concurrent load suite for the KoTH stack.")
    parser.add_argument("--host", default="127.0.0.1", help="Target host running the competition stack.")
    parser.add_argument("--targets", help="Comma-separated target list. Defaults to all machines.")
    parser.add_argument("--requests", type=int, default=100, help="Requests/probes per target.")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent workers per target.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Per-request timeout in seconds.")
    parser.add_argument("--json-out", help="Write structured results to this JSON file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = selected_targets(args.targets)
    summaries = [run_target(args.host, target, args.requests, args.concurrency, args.timeout) for target in targets]

    rows = []
    for item in summaries:
        latency = item["latency"]
        rows.append(
            [
                item["target"],
                item["protocol"],
                str(item["successes"]),
                str(item["failures"]),
                f"{item['success_rate']:.2f}%",
                f"{item['throughput_rps']:.2f}",
                f"{latency['p95_ms']:.2f}",
                item["sample_detail"],
            ]
        )

    print_table(["Target", "Proto", "OK", "Fail", "Success", "RPS", "P95 ms", "Detail"], rows)

    if args.json_out:
        write_json(
            args.json_out,
            {
                "host": args.host,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "summaries": summaries,
            },
        )

    return 0 if all(item["failures"] == 0 for item in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
