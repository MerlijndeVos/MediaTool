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
ICON_SRC="$ROOT/packaging/icons/media-tool.svg"
ICON_PNG="$ROOT/packaging/icons/media-tool.png"

cd "$ROOT"

if [[ ! -x "$DIST/MediaTool" ]]; then
  echo "Missing $DIST/MediaTool — run pyinstaller packaging/media-tool.spec first." >&2
  exit 1
fi

if [[ ! -f "$ICON_SRC" ]]; then
  echo "Missing icon: $ICON_SRC" >&2
  exit 1
fi

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

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

# appimagetool requires a 256x256 PNG named after Icon= in the .desktop file
mkdir -p "$(dirname "$ICON_PNG")"
if [[ -f "$ICON_PNG" ]]; then
  :
elif command -v rsvg-convert >/dev/null 2>&1; then
  rsvg-convert -w 256 -h 256 "$ICON_SRC" -o "$ICON_PNG"
elif command -v convert >/dev/null 2>&1; then
  convert -background none -resize 256x256 "$ICON_SRC" "$ICON_PNG"
else
  echo "Need rsvg-convert (librsvg2-bin) or ImageMagick to build the AppImage icon." >&2
  exit 1
fi

cp "$ICON_PNG" "$APPDIR/media-tool.png"
cp "$ICON_PNG" "$APPDIR/.DirIcon"
cp "$ICON_PNG" "$APPDIR/usr/share/icons/hicolor/256x256/apps/media-tool.png"

if ! command -v appimagetool >/dev/null 2>&1; then
  echo "appimagetool not found. Install from https://github.com/AppImage/AppImageKit" >&2
  exit 1
fi

mkdir -p "$OUT"
ARCH="$ARCH" appimagetool "$APPDIR" "$APPIMAGE"
echo "Created $APPIMAGE"
