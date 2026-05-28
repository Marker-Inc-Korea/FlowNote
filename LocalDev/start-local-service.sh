#!/bin/zsh
set -euo pipefail

service="${1:-}"
repo_dir="/Users/truds/Projects/Project/FlowNote"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

case "$service" in
  api)
    cd "$repo_dir/services/api"
    exec /opt/homebrew/bin/npm run start
    ;;
  web)
    cd "$repo_dir/apps/web"
    exec /opt/homebrew/bin/npm run dev
    ;;
  *)
    echo "Usage: $0 {api|web}" >&2
    exit 64
    ;;
esac
