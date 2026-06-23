#!/bin/zsh
set -euo pipefail

service="${1:-}"
script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_dir="$(cd "$script_dir/.." && pwd)"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

case "$service" in
  api)
    cd "$repo_dir/services/api"
    exec /opt/homebrew/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 5184
    ;;
  *)
    echo "Usage: $0 {api}" >&2
    exit 64
    ;;
esac
