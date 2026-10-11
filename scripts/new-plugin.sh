#!/usr/bin/env bash
#
# Materialise the backend + frontend plugin templates with a plugin's name substituted in.
#
#   ./scripts/new-plugin.sh --name connect --title "Care Connect" \
#       --description "Teleconsultation for CARE"
#
# Produces independent Git repositories at $OUT/care/care_connect and $OUT/care_connect_fe.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES="$SCRIPT_DIR/../templates"

NAME=""
TITLE=""
DESCRIPTION=""
OUT="$(cd "$SCRIPT_DIR/.." && pwd)"
PORT=""
API_URL=""

usage() {
  cat <<'EOF'
Usage: new-plugin.sh --name <short-name> [options]

  --name         Short lowercase plugin name, e.g. "connect"  (required)
  --title        Human readable title       [default: "Care <Name>"]
  --description  One-line description       [default: "<Title> plugin for CARE"]
  --out          Workspace root             [default: this scaffold checkout]
  --port         Frontend preview port      [default: workspace config, then available port]
  --api-url      Standalone backend URL     [default: workspace config, then http://127.0.0.1:9000]

Creates independent Git repositories at <out>/care/care_<name> (Django) and
<out>/care_<name>_fe (Vite), with no commits or remotes. Existing plugin
repositories are preserved on reruns. <out>/care must already be a Git checkout.
Excludes the backend plugin through care's local Git info/exclude file.
Reads <out>/care-scaffold.env when present. CLI options override its defaults.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name|--title|--description|--out|--port|--api-url)
      [[ $# -ge 2 && -n "$2" ]] || { echo "error: $1 requires a value" >&2; exit 1; } ;;
  esac
  case "$1" in
    --name)        NAME="$2"; shift 2 ;;
    --title)       TITLE="$2"; shift 2 ;;
    --description) DESCRIPTION="$2"; shift 2 ;;
    --out)         OUT="$2"; shift 2 ;;
    --port)        PORT="$2"; shift 2 ;;
    --api-url)     API_URL="$2"; shift 2 ;;
    -h|--help)     usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

[[ -n "$NAME" ]] || { echo "error: --name is required" >&2; usage; exit 1; }
[[ "$NAME" =~ ^[a-z][a-z0-9_]*$ ]] || {
  echo "error: --name must be lowercase alphanumeric/underscore, e.g. 'connect'" >&2; exit 1
}
command -v git >/dev/null || { echo "error: git is required" >&2; exit 1; }

CAPITALISED="$(tr '[:lower:]' '[:upper:]' <<<"${NAME:0:1}")${NAME:1}"
PLUGIN_SNAKE="care_${NAME}"
PLUGIN_FE="care_${NAME}_fe"
PLUGIN_FED_NAME="care_${NAME}"
PLUGIN_PREFIX="$(tr '[:lower:]' '[:upper:]' <<<"$NAME")"
I18N_PREFIX="${NAME}__"
PLUGIN_ROUTE="$NAME"
PLUGIN_CONTAINER="care-${NAME}-container"
PLUGIN_CLASS="Care${CAPITALISED}"
TITLE="${TITLE:-Care $CAPITALISED}"
DESCRIPTION="${DESCRIPTION:-$TITLE plugin for CARE}"

[[ -d "$OUT" ]] || { echo "error: workspace does not exist: $OUT" >&2; exit 1; }
OUT="$(cd "$OUT" && pwd -P)"
CARE="$OUT/care"
BE_OUT="$CARE/$PLUGIN_SNAKE"
FE_OUT="$OUT/$PLUGIN_FE"

require_git_root() {
  local root
  [[ ! -L "$1" ]] || {
    echo "error: $1 must be a real checkout directory, not a symlink" >&2; exit 1;
  }
  root="$(git -C "$1" rev-parse --show-toplevel 2>/dev/null)" || {
    echo "error: $1 must be an independent Git checkout" >&2; exit 1;
  }
  [[ "$(cd "$1" && pwd -P)" == "$(cd "$root" && pwd -P)" ]] || {
    echo "error: $1 belongs to parent repository $root; expected its own Git root" >&2; exit 1;
  }
}

require_git_root "$CARE"
NEW_ROOTS=()
BE_NEW=""
FE_NEW=""
for d in "$BE_OUT" "$FE_OUT"; do
  if [[ -e "$d" || -L "$d" ]]; then
    require_git_root "$d"
    echo "Preserving existing plugin repository: $d"
  else
    NEW_ROOTS+=("$d")
    if [[ "$d" == "$BE_OUT" ]]; then BE_NEW="$d"; else FE_NEW="$d"; fi
  fi
done

if [[ -n "$FE_NEW" ]]; then
SETTINGS="$(python3 - "$PORT" "$FE_OUT" "$API_URL" <<'PY'
import errno
import hashlib
from pathlib import Path
import re
import shlex
import socket
import sys
from urllib.parse import urlsplit

requested, output, api_url = sys.argv[1:]
workspace = Path(output).parent
env_path = workspace / "care-scaffold.env"
saved = {}
if env_path.exists():
    try:
        for line in env_path.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, separator, raw = line.partition("=")
            key = key.strip()
            if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or key in saved:
                raise ValueError(f"invalid or duplicate entry: {key}")
            value = shlex.split(raw, comments=True)
            if len(value) > 1:
                raise ValueError(f"invalid value for {key}")
            saved[key] = value[0] if value else ""
    except (OSError, ValueError) as error:
        sys.exit(f"error: {env_path}: {error}")

def valid_port(value):
    return value.isascii() and value.isdecimal() and 1024 <= int(value) <= 65535

if not api_url:
    if saved.get("CARE_API_PORT"):
        if not valid_port(saved["CARE_API_PORT"]):
            sys.exit(f"error: {env_path}: CARE_API_PORT must be an integer from 1024 to 65535")
        api_url = f"http://localhost:{int(saved['CARE_API_PORT'])}"
    else:
        api_url = saved.get("CARE_API_URL") or "http://127.0.0.1:9000"
try:
    url = urlsplit(api_url)
    if url.scheme not in {"http", "https"} or not url.hostname or any(c.isspace() for c in api_url):
        raise ValueError("--api-url must be an absolute HTTP(S) URL without whitespace")
    url.port  # Validate an explicitly supplied port.
except ValueError as error:
    sys.exit(f"error: {error}")

def available(port):
    sockets = []
    try:
        for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
            try:
                sock = socket.socket(family, socket.SOCK_STREAM)
                sockets.append(sock)
                sock.bind((address, port))
            except OSError as error:
                if family == socket.AF_INET6 and error.errno in {
                    errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL, errno.EPROTONOSUPPORT,
                }:
                    continue
                if error.errno == errno.EADDRINUSE:
                    return False
                sys.exit(f"error: cannot check localhost port {port}: {error}")
        return True
    finally:
        for sock in sockets:
            sock.close()

reserved = set()
for config in workspace.glob("care_*_fe/vite.config.ts"):
    reserved.update(int(value) for value in re.findall(r"\bport:\s*(\d+)", config.read_text()))
selected = requested or saved.get("PLUGIN_PORT", "")
if selected and not valid_port(selected):
    sys.exit("error: --port / PLUGIN_PORT must be an integer from 1024 to 65535")
if not requested and selected and int(selected) in reserved:
    selected = ""  # The first plugin already owns the configured workspace port.
if selected:
    port = int(selected)
    if not available(port):
        sys.exit(f"error: port {port} is already in use; choose another --port")
else:
    # Distinct generated plugins get different starting points even before they run.
    seed = int.from_bytes(hashlib.sha256(str(Path(output).resolve()).encode()).digest()[:4], "big")
    reserved.update(int(value) for key, value in saved.items()
                    if key.endswith("_PORT") and valid_port(value))
    for offset in range(30000):
        port = 18000 + (seed + offset) % 30000
        if port not in reserved and available(port):
            break
    else:
        sys.exit("error: no available plugin port from 18000 to 47999")
print(port)
print(api_url)
PY
)"
PORT="${SETTINGS%%$'\n'*}"
API_URL="${SETTINGS#*$'\n'}"
fi

# This is local Git metadata, never a tracked edit to the core checkout. Resolve
# through Git so separate gitdirs and linked worktrees also use their own exclude.
EXCLUDE="$(git -C "$CARE" rev-parse --git-path info/exclude)"
[[ "$EXCLUDE" == /* ]] || EXCLUDE="$CARE/$EXCLUDE"
mkdir -p "$(dirname "$EXCLUDE")"
if ! grep -Fqx "/$PLUGIN_SNAKE/" "$EXCLUDE" 2>/dev/null; then
  printf '\n/%s/\n' "$PLUGIN_SNAKE" >> "$EXCLUDE"
fi

if [[ ${#NEW_ROOTS[@]} -eq 0 ]]; then
  echo "Both plugin repositories already exist; no template or configuration files changed."
  exit 0
fi

if [[ -n "$BE_NEW" ]]; then
  cp -R "$TEMPLATES/backend" "$BE_OUT"
  mv "$BE_OUT/__PLUGIN_SNAKE__" "$BE_OUT/$PLUGIN_SNAKE"
fi
[[ -z "$FE_NEW" ]] || cp -R "$TEMPLATES/frontend" "$FE_OUT"

python3 - "$BE_NEW" "$FE_NEW" \
  "$PLUGIN_SNAKE" "$PLUGIN_FED_NAME" "$PLUGIN_FE" "$PLUGIN_PREFIX" \
  "$PLUGIN_CLASS" "$PLUGIN_CONTAINER" "$PLUGIN_ROUTE" "$PORT" \
  "$I18N_PREFIX" "$TITLE" "$DESCRIPTION" "$API_URL" <<'PY'
import html
import json
from pathlib import Path
import re
import sys

keys = ("PLUGIN_SNAKE", "PLUGIN_FED_NAME", "PLUGIN_FE", "PLUGIN_PREFIX",
        "PLUGIN_CLASS", "PLUGIN_CONTAINER", "PLUGIN_ROUTE", "PLUGIN_PORT",
        "I18N_PREFIX", "PLUGIN_TITLE", "PLUGIN_DESCRIPTION", "PLUGIN_API_URL")
values = dict(zip((f"__{key}__" for key in keys), sys.argv[3:]))
pattern = re.compile("|".join(map(re.escape, values)))
for root in sys.argv[1:3]:
    if not root:
        continue
    for path in Path(root).rglob("*"):
        if not path.is_file():
            continue
        replacements = values.copy()
        for key in ("__PLUGIN_TITLE__", "__PLUGIN_DESCRIPTION__", "__PLUGIN_API_URL__"):
            if path.suffix in {".json", ".py", ".ts", ".tsx"}:
                replacements[key] = json.dumps(values[key], ensure_ascii=False)[1:-1]
            elif path.suffix == ".html":
                replacements[key] = html.escape(values[key])
        path.write_text(pattern.sub(lambda match: replacements[match.group()], path.read_text()))
PY

# Fail loudly rather than shipping a half-substituted scaffold.
if grep -rl '__PLUGIN_\|__I18N_PREFIX__' "${NEW_ROOTS[@]}" >/dev/null 2>&1; then
  echo "error: unsubstituted placeholders remain:" >&2
  grep -rn '__PLUGIN_\|__I18N_PREFIX__' "${NEW_ROOTS[@]}" >&2
  exit 1
fi

for d in "${NEW_ROOTS[@]}"; do
  git init --quiet "$d"
  echo "Created independent Git repository (no commits or remotes): $d"
done

if [[ -n "$FE_NEW" ]]; then
  echo "Preview: http://localhost:$PORT (strict port; startup fails if it becomes occupied)"
  echo "Standalone API: $API_URL"
fi

cat <<EOF

Next:
  Load the stack configured by bootstrap.prompt.md:

       source "\$WORKSPACE/care-scaffold.env"

  1. Follow bootstrap.prompt.md Phase 6 to mount the backend repository using
     .agent/plugin.compose.yaml and register it through ADDITIONAL_PLUGS.
     Keep both plugins in their own repositories at the paths above. Do not add
     them as scaffold submodules or edit tracked files in either core checkout.

  2. Follow bootstrap.prompt.md section 6.2 to enable the frontend through the host
     process environment using the port in "$FE_OUT/vite.config.ts".

  3. cd "$FE_OUT" && npm install && npm run dev
EOF
