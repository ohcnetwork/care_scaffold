#!/usr/bin/env bash
#
# Materialise the backend + frontend plugin templates with a plugin's name substituted in.
#
#   ./scripts/new-plugin.sh --name connect --title "Care Connect" \
#       --description "Teleconsultation for CARE" --out ~/work
#
# Produces  $OUT/care_connect  and  $OUT/care_connect_fe.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES="$SCRIPT_DIR/../templates"

NAME=""
TITLE=""
DESCRIPTION=""
OUT="$PWD"
PORT="4173"

usage() {
  cat <<'EOF'
Usage: new-plugin.sh --name <short-name> [options]

  --name         Short lowercase plugin name, e.g. "connect"  (required)
  --title        Human readable title       [default: "Care <Name>"]
  --description  One-line description       [default: "<Title> plugin for CARE"]
  --out          Output directory           [default: current directory]
  --port         Frontend preview port      [default: 4173]

Creates <out>/care_<name> (Django) and <out>/care_<name>_fe (Vite).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)        NAME="$2"; shift 2 ;;
    --title)       TITLE="$2"; shift 2 ;;
    --description) DESCRIPTION="$2"; shift 2 ;;
    --out)         OUT="$2"; shift 2 ;;
    --port)        PORT="$2"; shift 2 ;;
    -h|--help)     usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

[[ -n "$NAME" ]] || { echo "error: --name is required" >&2; usage; exit 1; }
[[ "$NAME" =~ ^[a-z][a-z0-9_]*$ ]] || {
  echo "error: --name must be lowercase alphanumeric/underscore, e.g. 'connect'" >&2; exit 1
}

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

BE_OUT="$OUT/$PLUGIN_SNAKE"
FE_OUT="$OUT/$PLUGIN_FE"

for d in "$BE_OUT" "$FE_OUT"; do
  [[ -e "$d" ]] && { echo "error: $d already exists — refusing to overwrite" >&2; exit 1; }
done

mkdir -p "$OUT"
cp -R "$TEMPLATES/backend"  "$BE_OUT"
cp -R "$TEMPLATES/frontend" "$FE_OUT"

mv "$BE_OUT/__PLUGIN_SNAKE__" "$BE_OUT/$PLUGIN_SNAKE"

substitute() {
  # macOS and GNU sed disagree about -i; write to a temp file instead.
  local file="$1" tmp
  tmp="$(mktemp)"
  sed \
    -e "s|__PLUGIN_SNAKE__|$PLUGIN_SNAKE|g" \
    -e "s|__PLUGIN_FED_NAME__|$PLUGIN_FED_NAME|g" \
    -e "s|__PLUGIN_FE__|$PLUGIN_FE|g" \
    -e "s|__PLUGIN_PREFIX__|$PLUGIN_PREFIX|g" \
    -e "s|__PLUGIN_CLASS__|$PLUGIN_CLASS|g" \
    -e "s|__PLUGIN_CONTAINER__|$PLUGIN_CONTAINER|g" \
    -e "s|__PLUGIN_ROUTE__|$PLUGIN_ROUTE|g" \
    -e "s|__PLUGIN_PORT__|$PORT|g" \
    -e "s|__I18N_PREFIX__|$I18N_PREFIX|g" \
    -e "s|__PLUGIN_TITLE__|$TITLE|g" \
    -e "s|__PLUGIN_DESCRIPTION__|$DESCRIPTION|g" \
    "$file" >"$tmp"
  mv "$tmp" "$file"
}

export -f substitute 2>/dev/null || true
while IFS= read -r -d '' file; do
  substitute "$file"
done < <(find "$BE_OUT" "$FE_OUT" -type f -print0)

# Fail loudly rather than shipping a half-substituted scaffold.
if grep -rl '__PLUGIN_\|__I18N_PREFIX__' "$BE_OUT" "$FE_OUT" >/dev/null 2>&1; then
  echo "error: unsubstituted placeholders remain:" >&2
  grep -rn '__PLUGIN_\|__I18N_PREFIX__' "$BE_OUT" "$FE_OUT" >&2
  exit 1
fi

cat <<EOF

Created:
  $BE_OUT
  $FE_OUT

Next:
  1. Register the backend in \$CARE_BE/plug_config.py:

       ${PLUGIN_SNAKE} = Plug(
           name="${PLUGIN_SNAKE}",
           package_name="${PLUGIN_SNAKE}",
           version="",
           configs={"${PLUGIN_PREFIX}_ENABLED": True},
       )
       plugs = [${PLUGIN_SNAKE}, ...]

     Move it into the backend checkout as a REAL directory (a symlink breaks
     'docker build', which cannot follow links out of the build context):

       mv "$BE_OUT" "\$CARE_BE/${PLUGIN_SNAKE}"

     Then rebuild the image - plugins are pip-installed at image build time:

       cd "\$CARE_BE" && make down && make build && make up
       # NOT 'make teardown' - that deletes the database volume.

  2. Enable the frontend in \$CARE_FE/.env.local (append comma-separated if it
     already has entries), then restart the EXISTING dev server - do not start
     a second one:

       REACT_ENABLED_APPS=ohcnetwork/${PLUGIN_FE}@localhost:${PORT}/assets/remoteEntry.js

  3. cd "$FE_OUT" && npm install && npm run dev
EOF
