#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
WEB_DIR="$ROOT_DIR/web"
STATIC_DIR="$ROOT_DIR/app/static"
NEXT_OUT_DIR="$WEB_DIR/out"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--skip-install]

Builds the Next.js frontend located in ./web and syncs the generated static
artifacts into app/static so FastAPI can serve them.

Options:
  --skip-install   Skip running npm install (assumes node_modules already exists)
USAGE
}

SKIP_INSTALL=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --skip-install)
      SKIP_INSTALL=true
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm is required to build the frontend." >&2
  exit 1
fi

pushd "$WEB_DIR" >/dev/null
if [[ "$SKIP_INSTALL" != "true" || ! -d node_modules ]]; then
  npm install
fi
: "${NEXT_PUBLIC_API_BASE:=}"
export NEXT_PUBLIC_API_BASE
npm run build
popd >/dev/null

if [[ ! -d "$NEXT_OUT_DIR" ]]; then
  echo "Error: build output not found at $NEXT_OUT_DIR" >&2
  exit 1
fi

rm -rf "$STATIC_DIR"
mkdir -p "$STATIC_DIR"
cp -R "$NEXT_OUT_DIR"/. "$STATIC_DIR"/

if [[ -f "$STATIC_DIR/portal/index.html" ]]; then
  cp "$STATIC_DIR/portal/index.html" "$STATIC_DIR/portal.html"
fi

if [[ -f "$STATIC_DIR/index.html" ]]; then
  echo "Frontend assets copied to app/static." >&2
else
  echo "Warning: index.html missing from build output." >&2
fi
