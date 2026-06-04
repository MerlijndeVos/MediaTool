#!/usr/bin/env bash
# Build a macOS .dmg from the PyInstaller bundle (run on macOS after pyinstaller).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -n "${1:-}" ]]; then
  VERSION="$1"
else
  VERSION="$(PYTHONPATH="$ROOT" python -c "from core.version import read_pyproject_version; print(read_pyproject_version())")"
fi
DIST="$ROOT/dist"
OUT="$ROOT/packaging/dist"
APP_NAME="Media Tool.app"
DMG_NAME="MediaTool-${VERSION}-macos.dmg"

cd "$ROOT"

if [[ ! -d "$DIST/$APP_NAME" ]]; then
  echo "Missing $DIST/$APP_NAME — run pyinstaller packaging/media-tool.spec first." >&2
  exit 1
fi

mkdir -p "$OUT"
STAGING="$OUT/dmg-staging"
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp -R "$DIST/$APP_NAME" "$STAGING/"

hdiutil create -volname "Media Tool" -srcfolder "$STAGING" -ov -format UDZO "$OUT/$DMG_NAME"
rm -rf "$STAGING"
echo "Created $OUT/$DMG_NAME"
