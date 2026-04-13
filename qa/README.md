# QA Test Harness

This directory adds two additive test suites for the main competition host:

- `load_suite.py`: concurrent service-level load checks across the exposed port matrix.
- `vuln_suite.py`: machine-specific vulnerability validation using safe proof payloads such as `printf h5a_ok`.

These scripts are intentionally isolated from the runtime configs and do not require changes to the existing stacks.

## Safety

Run these only against your own KoTH deployment. The vuln suite performs real exploit probes against intentionally vulnerable services, but keeps the payloads non-destructive and marker-based.

## Prerequisites

- Python 3.10+
- Optional external clients for broader protocol coverage:
  - `smbclient` for `machineH3A`
  - `mongosh` for `machineH6B`
  - `snmpwalk` for `machineH7A`
  - `rsync` for `machineH7C`

If an optional client is missing, the vuln suite falls back to a weaker fingerprint and returns `WARN` instead of `PASS`.

## Usage

Run the load suite against the full stack:

```bash
python3 qa/load_suite.py --host 127.0.0.1 --requests 200 --concurrency 20 --json-out qa/load-results.json
```

Run only a subset:

```bash
python3 qa/load_suite.py --host 127.0.0.1 --targets machineH5A,machineH5B,machineH5C
```

Run the vuln suite:

```bash
python3 qa/vuln_suite.py --host 127.0.0.1 --json-out qa/vuln-results.json
```

Treat warning-level partial coverage as a failing run:

```bash
python3 qa/vuln_suite.py --host 127.0.0.1 --fail-on-warn
```

## Output

Both suites print a compact terminal table and can also emit JSON for CI or archival use.

- `load_suite.py` returns non-zero if any target has failed probes.
- `vuln_suite.py` returns non-zero on any `FAIL`, and also on `WARN` when `--fail-on-warn` is set.

## Coverage Notes

- The load suite uses protocol-aware probes where practical:
  - HTTP/HTTPS GETs for web services
  - Redis `PING`
  - rsync banner reads
  - SNMP UDP `sysDescr` requests
  - raw TCP connects for services such as SMB, MongoDB, and distccd
- The vuln suite automates strong proofs for the web-heavy machines:
  - H1A upload, H1C command injection
  - H2A Jenkins script console, H2B SQLi + command injection, H2C default creds
  - H4A/H4B/H4C execution chains
  - H5A/H5B/H5C RCE checks
  - H6C Heartbleed leak
  - H7B traversal-to-admin-exec, H7C anonymous rsync write
  - H8A blank-root phpMyAdmin, H8B SSTI, H8C Ignition RCE
- A few protocol-heavy boxes are deliberately marked as partial when helper tools are unavailable rather than silently skipped.
