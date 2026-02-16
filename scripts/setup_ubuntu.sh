#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
REQUIREMENTS_FILE="$ROOT_DIR/requirements.txt"
SYSTEMD_UNIT_SOURCE="$ROOT_DIR/systemd/wol-web.service"
SYSTEMD_UNIT_DEST="/etc/systemd/system/wol-web.service"

if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

function usage() {
  cat <<'USAGE'
Usage: scripts/setup_ubuntu.sh [options]

Provision and (optionally) deploy wol-web on Ubuntu. When run locally it installs
dependencies, builds the Next.js bundle, and configures systemd. When run with
--remote-host it SSHes into the destination, syncs this repository, and executes the
same setup script remotely.

Local options:
  --skip-apt              Skip apt update/install (set if packages already installed).
  --install-systemd       Install and enable the wol-web systemd service.
  --api-base <url>        Value for NEXT_PUBLIC_API_BASE during the frontend build (default: empty).

Remote deployment options:
  --remote-host <user@host>    SSH destination that should receive the repo.
  --remote-path <path>         Remote directory to sync into (default: ~/wol-web).
  --remote-ssh-opts "<opts>"   Extra options for ssh/rsync (e.g. "-i ~/.ssh/id_ed25519 -p 2222").

Examples:
  ./scripts/setup_ubuntu.sh --install-systemd
  ./scripts/setup_ubuntu.sh --remote-host ubuntu@192.168.123.112 --remote-path /opt/wol-web --install-systemd

USAGE
}

function ensure_nodesource() {
  if command -v node >/dev/null 2>&1; then
    local major
    major="$(node -v | sed -E 's/^v([0-9]+).*/\1/')"
    if [[ "$major" -ge 20 ]]; then
      return
    fi
    echo "Detected Node.js $(node -v); upgrading to Node.js 20.x..." >&2
  else
    echo "Installing Node.js 20.x..." >&2
  fi

  curl -fsSL https://deb.nodesource.com/setup_20.x | $SUDO bash -
  $SUDO apt-get install -y nodejs
}

# ---------- argument parsing (remote flags first) ----------
REMOTE_HOST=""
REMOTE_PATH="~/wol-web"
REMOTE_SSH_OPTS=""

NON_REMOTE_ARGS=()
if [[ $# -eq 0 ]]; then
  :
else
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --remote-host)
        REMOTE_HOST="${2:-}"
        shift 2
        ;;
      --remote-path)
        REMOTE_PATH="${2:-}"
        shift 2
        ;;
      --remote-ssh-opts)
        REMOTE_SSH_OPTS="${2:-}"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        NON_REMOTE_ARGS+=("$1")
        shift
        ;;
    esac
  done
fi

set -- "${NON_REMOTE_ARGS[@]}"
PASSTHRU_ARGS=("$@")

SKIP_APT=false
INSTALL_SYSTEMD=false
NEXT_PUBLIC_API_BASE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-apt)
      SKIP_APT=true
      shift
      ;;
    --install-systemd)
      INSTALL_SYSTEMD=true
      shift
      ;;
    --api-base)
      NEXT_PUBLIC_API_BASE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -n "$REMOTE_HOST" ]]; then
  # Prepare SSH command arrays.
  SSH_CMD=(ssh)
  if [[ -n "$REMOTE_SSH_OPTS" ]]; then
    # shellcheck disable=SC2206
    SSH_EXTRA=($REMOTE_SSH_OPTS)
    SSH_CMD+=("${SSH_EXTRA[@]}")
  fi

  echo ">>> Syncing repository to $REMOTE_HOST:$REMOTE_PATH"
  "${SSH_CMD[@]}" "$REMOTE_HOST" "mkdir -p '$REMOTE_PATH'"

  EXCLUDES=(--exclude='.git' --exclude='.venv' --exclude='node_modules' --exclude='app/static' --exclude='web/.next' --exclude='web/out')
  if command -v rsync >/dev/null 2>&1; then
    RSYNC_CMD=(rsync -az --delete)
    RSYNC_CMD+=("${EXCLUDES[@]}")
    if [[ -n "$REMOTE_SSH_OPTS" ]]; then
      RSYNC_CMD+=("-e" "ssh $REMOTE_SSH_OPTS")
    fi
    RSYNC_CMD+=("$ROOT_DIR/", "$REMOTE_HOST:$REMOTE_PATH/")
    "${RSYNC_CMD[@]}"
  else
    TAR_ARGS=(-cf - "${EXCLUDES[@]}")
    tar "${TAR_ARGS[@]}" -C "$ROOT_DIR" . | "${SSH_CMD[@]}" "$REMOTE_HOST" "rm -rf '$REMOTE_PATH' && mkdir -p '$REMOTE_PATH' && tar -xf - -C '$REMOTE_PATH'"
  fi

  FORWARD_SERIALIZED=""
  if [[ ${#PASSTHRU_ARGS[@]} -gt 0 ]]; then
    FORWARD_SERIALIZED="$(printf " %q" "${PASSTHRU_ARGS[@]}")"
  fi

  echo ">>> Executing setup on $REMOTE_HOST"
  "${SSH_CMD[@]}" "$REMOTE_HOST" "cd '$REMOTE_PATH' && ./scripts/setup_ubuntu.sh${FORWARD_SERIALIZED}"
  exit 0
fi

# ---------- local provisioning ----------
if [[ "$SKIP_APT" != "true" ]]; then
  $SUDO apt-get update
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y python3 python3-venv python3-pip etherwake curl
fi

ensure_nodesource

if [[ "$SKIP_APT" != "true" ]]; then
  $SUDO apt-get install -y build-essential
fi

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$REQUIREMENTS_FILE"

pushd "$ROOT_DIR" >/dev/null
export NEXT_PUBLIC_API_BASE
./scripts/build_frontend.sh
popd >/dev/null

if [[ "$INSTALL_SYSTEMD" == "true" ]]; then
  if [[ ! -f "$SYSTEMD_UNIT_SOURCE" ]]; then
    echo "Systemd unit file not found at $SYSTEMD_UNIT_SOURCE" >&2
    exit 1
  fi
  $SUDO cp "$SYSTEMD_UNIT_SOURCE" "$SYSTEMD_UNIT_DEST"
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now wol-web
  $SUDO systemctl status wol-web --no-pager
fi

cat <<'DONE'

✅ Provisioning complete.

To start the API in the current shell (without systemd):
  source .venv/bin/activate
  python -m app.main

DONE
