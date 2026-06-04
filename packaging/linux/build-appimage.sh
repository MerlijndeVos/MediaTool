#!/usr/bin/env bash
# Build a Linux AppImage from the PyInstaller onedir (run on Linux after pyinstaller).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="${1:-0.1.0}"
ARCH="${ARCH:-$(uname -m)}"
DIST="$ROOT/dist/MediaTool"
OUT="$ROOT/packaging/dist"
APPDIR="$OUT/MediaTool.AppDir"
APPIMAGE="$OUT/MediaTool-${VERSION}-linux-${ARCH}.AppImage"

cd "$ROOT"

if [[ ! -x "$DIST/MediaTool" ]]; then
  echo "Missing $DIST/MediaTool — run pyinstaller packaging/media-tool.spec first." >&2
  exit 1
fi

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications"

cp -a "$DIST/." "$APPDIR/usr/bin/"
ln -sf usr/bin/MediaTool "$APPDIR/AppRun"

cat > "$APPDIR/media-tool.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Media Tool
Exec=MediaTool
Icon=media-tool
Categories=AudioVideo;Video;
Terminal=false
EOF

cp "$APPDIR/media-tool.desktop" "$APPDIR/usr/share/applications/"

if ! command -v appimagetool >/dev/null 2>&1; then
  echo "appimagetool not found. Install from https://github.com/AppImage/AppImageKit" >&2
  exit 1
fi

mkdir -p "$OUT"
ARCH="$ARCH" appimagetool "$APPDIR" "$APPIMAGE"
echo "Created $APPIMAGE"
