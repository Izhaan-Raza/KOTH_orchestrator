#!/usr/bin/env bash
set -euo pipefail

REFEREE_DIR="/opt/KOTH_orchestrator/repo/referee-server"
SERIES_CSV="1,2,3,4,5,6,7,8"
HOST_FILTER=""
PULL_LATEST=0

usage() {
  cat <<'EOF'
Usage: prebuild_series_cache.sh [options]

Pre-build challenge images on all configured nodes so the referee's first
competition start does not spend minutes building Docker images.

Options:
  --referee-dir PATH   Referee directory containing .env (default: /opt/KOTH_orchestrator/repo/referee-server)
  --series LIST        Comma-separated series numbers to prebuild (default: 1,2,3,4,5,6,7,8)
  --hosts LIST         Comma-separated host/IP filter matching NODE_HOSTS entries
  --pull               Run docker-compose build --pull
  -h, --help           Show this help text
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --referee-dir)
      REFEREE_DIR="$2"
      shift 2
      ;;
    --series)
      SERIES_CSV="$2"
      shift 2
      ;;
    --hosts)
      HOST_FILTER="$2"
      shift 2
      ;;
    --pull)
      PULL_LATEST=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -d "$REFEREE_DIR" ]]; then
  echo "Referee directory not found: $REFEREE_DIR" >&2
  exit 1
fi

if [[ ! -f "$REFEREE_DIR/.env" ]]; then
  echo "Missing referee env file: $REFEREE_DIR/.env" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$REFEREE_DIR/.env"
set +a

SSH_PRIVATE_KEY="${SSH_PRIVATE_KEY:-$HOME/.ssh/id_rsa}"
SSH_PORT="${SSH_PORT:-22}"
SSH_USER="${SSH_USER:-root}"
REMOTE_SERIES_ROOT="${REMOTE_SERIES_ROOT:-/opt/KOTH_orchestrator}"
NODE_HOSTS="${NODE_HOSTS:-}"
NODE_SSH_TARGETS="${NODE_SSH_TARGETS:-}"

if [[ -z "$NODE_HOSTS" ]]; then
  echo "NODE_HOSTS is empty in $REFEREE_DIR/.env" >&2
  exit 1
fi

IFS=',' read -r -a HOSTS <<<"$NODE_HOSTS"
IFS=',' read -r -a TARGETS <<<"$NODE_SSH_TARGETS"
IFS=',' read -r -a SERIES_LIST <<<"$SERIES_CSV"
IFS=',' read -r -a HOST_FILTERS <<<"$HOST_FILTER"

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

should_run_host() {
  local host="$1"
  if [[ ${#HOST_FILTERS[@]} -eq 0 || -z "$(trim "${HOST_FILTERS[*]}")" ]]; then
    return 0
  fi
  local item
  for item in "${HOST_FILTERS[@]}"; do
    item="$(trim "$item")"
    if [[ "$item" == "$host" ]]; then
      return 0
    fi
  done
  return 1
}

target_for_host() {
  local idx="$1"
  local host="$2"
  if [[ ${#TARGETS[@]} -gt 0 && -n "$(trim "${TARGETS[$idx]:-}")" ]]; then
    printf '%s' "$(trim "${TARGETS[$idx]}")"
    return
  fi
  printf '%s' "${SSH_USER}@${host}"
}

build_flag=""
if [[ "$PULL_LATEST" -eq 1 ]]; then
  build_flag="--pull"
fi

echo "== Prebuild Docker Cache =="
echo "Referee dir: $REFEREE_DIR"
echo "Remote series root: $REMOTE_SERIES_ROOT"
echo "SSH key: $SSH_PRIVATE_KEY"
echo "Series: $SERIES_CSV"
if [[ -n "$HOST_FILTER" ]]; then
  echo "Host filter: $HOST_FILTER"
fi
echo

failures=0

for idx in "${!HOSTS[@]}"; do
  host="$(trim "${HOSTS[$idx]}")"
  if ! should_run_host "$host"; then
    continue
  fi
  target="$(target_for_host "$idx" "$host")"
  echo "== Node: $host ($target) =="
  for series in "${SERIES_LIST[@]}"; do
    series="$(trim "$series")"
    if [[ -z "$series" ]]; then
      continue
    fi
    remote_dir="${REMOTE_SERIES_ROOT}/h${series}"
    echo "-- H${series}: validating compose"
    if ! ssh -i "$SSH_PRIVATE_KEY" -p "$SSH_PORT" "$target" \
      "cd '$remote_dir' && test -f docker-compose.yml && docker-compose config -q"; then
      echo "[FAIL] $host H${series}: compose validation failed" >&2
      failures=$((failures + 1))
      continue
    fi

    echo "-- H${series}: building images"
    if ! ssh -i "$SSH_PRIVATE_KEY" -p "$SSH_PORT" "$target" \
      "cd '$remote_dir' && docker-compose build $build_flag"; then
      echo "[FAIL] $host H${series}: build failed" >&2
      failures=$((failures + 1))
      continue
    fi

    echo "[OK] $host H${series}: cache warmed"
  done
  echo
done

if [[ "$failures" -gt 0 ]]; then
  echo "Prebuild completed with $failures failure(s)." >&2
  exit 1
fi

echo "Prebuild completed successfully."
