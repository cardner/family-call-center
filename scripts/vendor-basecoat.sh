#!/usr/bin/env bash
#
# Vendor Basecoat CSS/JS (and optional Jinja macros) into the Flask app so the
# admin UI is self-contained and does not depend on a CDN at browse time.
#
# Style pack: default is the Vega bundle (basecoat.cdn.min.css). To use a named
# style pack instead (nova, maia, lyra, mira, luma, sera, rhea), set STYLE, e.g.
#   STYLE=maia ./scripts/vendor-basecoat.sh
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STYLE="${STYLE:-}"

CSS_DEST="$PROJECT_DIR/app/static/vendor/basecoat"
JS_DEST="$PROJECT_DIR/app/static/vendor/basecoat"
MACRO_DEST="$PROJECT_DIR/app/templates/components/basecoat"

NODE_MODULES="$PROJECT_DIR/node_modules/basecoat-css"

if [[ ! -d "$NODE_MODULES" ]]; then
  echo "Installing npm dependencies (basecoat-css)..."
  if [[ -f "$PROJECT_DIR/package-lock.json" ]]; then
    (cd "$PROJECT_DIR" && npm ci --no-audit --no-fund)
  else
    (cd "$PROJECT_DIR" && npm install --no-audit --no-fund)
  fi
fi

mkdir -p "$CSS_DEST" "$JS_DEST"

if [[ -n "$STYLE" ]]; then
  css_src="$NODE_MODULES/dist/basecoat-${STYLE}.cdn.min.css"
else
  css_src="$NODE_MODULES/dist/basecoat.cdn.min.css"
fi

if [[ ! -f "$css_src" ]]; then
  echo "Could not find Basecoat stylesheet at: $css_src" >&2
  echo "Available CDN stylesheets:" >&2
  ls "$NODE_MODULES/dist/" 2>/dev/null | grep -E '\.cdn\.min\.css$' >&2 || true
  exit 1
fi

cp "$css_src" "$CSS_DEST/basecoat.css"
echo "Vendored CSS -> app/static/vendor/basecoat/basecoat.css"

js_src="$NODE_MODULES/dist/js/all.min.js"
if [[ ! -f "$js_src" ]]; then
  echo "Could not find Basecoat JS at: $js_src" >&2
  exit 1
fi
cp "$js_src" "$JS_DEST/all.js"
echo "Vendored JS -> app/static/vendor/basecoat/all.js"

# Jinja macros are optional; the templates use semantic Basecoat classes directly
# and do not require these, but we copy them if present for reference/reuse.
# Always create the destination so downstream (Docker) copies do not fail.
mkdir -p "$MACRO_DEST"
if [[ -d "$NODE_MODULES/templates/jinja" ]]; then
  cp -R "$NODE_MODULES/templates/jinja/." "$MACRO_DEST/"
  echo "Vendored Jinja macros -> app/templates/components/basecoat/"
else
  echo "No Jinja macros directory found in basecoat-css package (optional); skipping."
fi

echo "Basecoat vendoring complete."
