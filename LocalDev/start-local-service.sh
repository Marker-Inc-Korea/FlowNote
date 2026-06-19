#!/bin/zsh
set -euo pipefail

service="${1:-}"
repo_dir="/Users/truds/Projects/Project/FlowNote"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

case "$service" in
  api)
    cd "$repo_dir/services/api"
    exec /opt/homebrew/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 5184
    ;;
  legacy-node-api)
    cd "$repo_dir/services/api/legacy-node"
    exec /opt/homebrew/bin/npm run start
    ;;
  legacy-web)
    cd "$repo_dir/apps/web/legacy-react-vite"
    exec /opt/homebrew/bin/npm run dev
    ;;
  *)
    echo "Usage: $0 {api|legacy-node-api|legacy-web}" >&2
    exit 64
    ;;
esac
