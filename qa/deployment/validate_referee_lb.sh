#!/usr/bin/env bash
set -euo pipefail

SERIES_ROOT="/opt/KOTH_orchestrator"
REFEREE_DIR="/opt/KOTH_orchestrator/repo/referee-server"
API_URL="http://127.0.0.1:8000"
API_KEY="${API_KEY:-}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --series-root)
      SERIES_ROOT="$2"
      shift 2
      ;;
    --referee-dir)
      REFEREE_DIR="$2"
      shift 2
      ;;
    --api-url)
      API_URL="$2"
      shift 2
      ;;
    --api-key)
      API_KEY="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 [--series-root PATH] [--referee-dir PATH] [--api-url URL] [--api-key KEY] [--dry-run]"
      exit 2
      ;;
  esac
done

PASS=0
FAIL=0
SERVICE_ACTIVE=0

pass() { echo "[PASS] $*"; PASS=$((PASS + 1)); }
fail() { echo "[FAIL] $*"; FAIL=$((FAIL + 1)); }

env_value() {
  local key="$1"
  local file="$2"
  local line
  line="$(grep -E "^${key}=" "$file" | tail -n 1 || true)"
  printf '%s' "${line#*=}"
}

run_in_referee_env() {
  local script="$1"
  if [[ -f "$REFEREE_DIR/.env" ]]; then
    (
      set -a
      # shellcheck disable=SC1091
      source "$REFEREE_DIR/.env"
      set +a
      cd "$REFEREE_DIR"
      eval "$script"
    )
  else
    (
      cd "$REFEREE_DIR"
      eval "$script"
    )
  fi
}

echo "== Referee + LB Validation =="
echo "Host: $(hostname)"
echo "Series root: $SERIES_ROOT"
echo "Referee dir: $REFEREE_DIR"
echo "API URL: $API_URL"
echo "Dry run: $DRY_RUN"
echo

for cmd in python3 curl jq grep awk ssh haproxy; do
  if command -v "$cmd" >/dev/null 2>&1; then
    pass "command exists: $cmd"
  else
    fail "missing command: $cmd"
  fi
done

if systemctl is-active --quiet chrony; then
  pass "chrony service active"
else
  fail "chrony service not active"
fi

if [[ -f "$REFEREE_DIR/.env" ]]; then
  pass ".env exists: $REFEREE_DIR/.env"
else
  fail ".env missing: $REFEREE_DIR/.env"
fi

if [[ -d "$REFEREE_DIR/.venv" ]]; then
  pass "python venv exists: $REFEREE_DIR/.venv"
else
  fail "python venv missing: $REFEREE_DIR/.venv"
fi

if haproxy -c -f /etc/haproxy/haproxy.cfg >/dev/null 2>&1; then
  pass "haproxy config valid"
else
  fail "haproxy config invalid"
fi

if systemctl is-active --quiet haproxy; then
  pass "haproxy service active"
else
  fail "haproxy service not active"
fi

if systemctl is-active --quiet koth-referee; then
  SERVICE_ACTIVE=1
fi

if [[ -f "$REFEREE_DIR/.env" ]]; then
  required_keys=(
    NODE_HOSTS
    NODE_PRIORITY
    SSH_USER
    SSH_PRIVATE_KEY
    REMOTE_SERIES_ROOT
    CONTAINER_NAME_TEMPLATE
    ADMIN_API_KEY
  )
  for k in "${required_keys[@]}"; do
    v="$(env_value "$k" "$REFEREE_DIR/.env")"
    if [[ -n "$v" ]]; then
      pass ".env key present: $k"
    else
      fail ".env key missing/empty: $k"
    fi
  done

  ctmpl="$(env_value "CONTAINER_NAME_TEMPLATE" "$REFEREE_DIR/.env")"
  if [[ "$ctmpl" == "machineH{series}{variant}" ]]; then
    pass "CONTAINER_NAME_TEMPLATE matches expected value"
  else
    fail "CONTAINER_NAME_TEMPLATE expected machineH{series}{variant}, got: $ctmpl"
  fi

  remote_root="$(env_value "REMOTE_SERIES_ROOT" "$REFEREE_DIR/.env")"
  if [[ "$remote_root" == "$SERIES_ROOT" ]]; then
    pass "REMOTE_SERIES_ROOT matches expected series root argument"
  else
    fail "REMOTE_SERIES_ROOT mismatch: env=$remote_root expected=$SERIES_ROOT"
  fi

  node_hosts="$(env_value "NODE_HOSTS" "$REFEREE_DIR/.env")"
  host_count="$(printf '%s' "$node_hosts" | awk -F',' '{print NF}')"
  if [[ "$host_count" -eq 3 ]]; then
    pass "NODE_HOSTS defines 3 challenge nodes"
  else
    fail "NODE_HOSTS should contain exactly 3 hosts, got: $node_hosts"
  fi
fi

if [[ -f "$REFEREE_DIR/setup_cli.py" ]]; then
  if run_in_referee_env "./.venv/bin/python -c 'from config import SETTINGS; SETTINGS.validate_runtime()' >/tmp/ref_config_check.out 2>/tmp/ref_config_check.err"; then
    pass "referee runtime configuration validates"
  else
    fail "referee runtime configuration invalid (see /tmp/ref_config_check.err)"
  fi

  if run_in_referee_env "./.venv/bin/python setup_cli.py --series 1 >/tmp/ref_setup_cli.out 2>/tmp/ref_setup_cli.err"; then
    pass "setup_cli.py --series 1 succeeded"
  else
    fail "setup_cli.py --series 1 failed (see /tmp/ref_setup_cli.err)"
  fi
else
  fail "setup_cli.py missing in referee dir"
fi

http_code="$(curl -s -o /tmp/ref_status.json -w '%{http_code}' "$API_URL/api/status" || true)"
if [[ "$http_code" == "200" ]]; then
  pass "referee API status endpoint reachable"
  if [[ "$SERVICE_ACTIVE" -eq 1 ]]; then
    pass "koth-referee service active"
  else
    pass "referee reachable in manual mode (uvicorn without systemd)"
  fi
  if jq -e '.competition_status and .current_series != null' /tmp/ref_status.json >/dev/null 2>&1; then
    pass "referee API status payload shape valid"
  else
    fail "referee API status payload malformed"
  fi
else
  if [[ "$SERVICE_ACTIVE" -eq 1 ]]; then
    pass "koth-referee service active"
  else
    fail "koth-referee service inactive and API unavailable"
  fi
  fail "referee API status endpoint not healthy (HTTP $http_code)"
fi

runtime_code="$(curl -s -o /tmp/ref_runtime.json -w '%{http_code}' "$API_URL/api/runtime" || true)"
if [[ "$runtime_code" == "200" ]]; then
  pass "referee API runtime endpoint reachable"
  if jq -e '.competition_status and .current_series != null and .active_jobs' /tmp/ref_runtime.json >/dev/null 2>&1; then
    pass "referee API runtime payload shape valid"
  else
    fail "referee API runtime payload malformed"
  fi
else
  fail "referee API runtime endpoint not healthy (HTTP $runtime_code)"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  if [[ -z "$API_KEY" ]]; then
    fail "dry run requested but --api-key was not provided"
  else
    auth_header=(-H "X-API-Key: $API_KEY")
    current_runtime="$(curl -sS "$API_URL/api/runtime" || true)"
    current_status="$(printf '%s' "$current_runtime" | jq -r '.competition_status // empty' 2>/dev/null || true)"
    if [[ "$current_status" == "running" ]]; then
      fail "dry run refused because the runtime is currently running; this validation must not mutate a live event"
    fi

    if curl -sS -X POST "${auth_header[@]}" "$API_URL/api/recover/validate" | jq -e '.valid != null' >/dev/null 2>&1; then
      pass "recovery validation endpoint reachable with admin key"
    else
      fail "recovery validation endpoint failed"
    fi

    runtime_after_validate="$(curl -sS "$API_URL/api/runtime" || true)"
    if printf '%s' "$runtime_after_validate" | jq -e '.competition_status == "paused" or .competition_status == "faulted" or .competition_status == "stopped"' >/dev/null 2>&1; then
      pass "runtime remains in a non-running state during non-destructive dry run"
    else
      fail "runtime entered an unexpected state during dry run"
    fi
  fi
fi

echo
echo "Summary: PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
echo "ALL CHECKS PASSED"
