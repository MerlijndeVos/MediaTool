#!/usr/bin/env bash
# Build a Linux AppImage from the PyInstaller onedir (run on Linux after pyinstaller).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -n "${1:-}" ]]; then
  VERSION="$1"
else
  VERSION="$(PYTHONPATH="$ROOT" python -c "from core.version import read_pyproject_version; print(read_pyproject_version())")"
fi
ARCH="${ARCH:-$(uname -m)}"
DIST="$ROOT/dist/Toolbox"
OUT="$ROOT/packaging/dist"
APPDIR="$OUT/Toolbox.AppDir"
APPIMAGE="$OUT/Toolbox-${VERSION}-linux-${ARCH}.AppImage"
ICON_SRC="$ROOT/packaging/icons/toolbox.svg"
ICON_PNG="$ROOT/packaging/icons/toolbox.png"

cd "$ROOT"

if [[ ! -x "$DIST/Toolbox" ]]; then
  echo "Missing $DIST/Toolbox — run pyinstaller packaging/toolbox.spec first." >&2
  exit 1
fi

if [[ ! -f "$ICON_SRC" ]]; then
  echo "Missing icon: $ICON_SRC" >&2
  exit 1
fi

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -a "$DIST/." "$APPDIR/usr/bin/"
ln -sf usr/bin/Toolbox "$APPDIR/AppRun"

cat > "$APPDIR/toolbox.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Toolbox
Exec=Toolbox
Icon=toolbox
Categories=AudioVideo;Video;
Terminal=false
EOF

cp "$APPDIR/toolbox.desktop" "$APPDIR/usr/share/applications/"

# appimagetool requires a 256x256 PNG named after Icon= in the .desktop file
if [[ ! -f "$ICON_PNG" ]]; then
  if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w 256 -h 256 "$ICON_SRC" -o "$ICON_PNG"
  elif command -v convert >/dev/null 2>&1; then
    convert -background none -resize 256x256 "$ICON_SRC" "$ICON_PNG"
  else
    echo "Missing $ICON_PNG and no rsvg-convert/ImageMagick to render from SVG." >&2
    exit 1
  fi
fi

cp "$ICON_PNG" "$APPDIR/toolbox.png"
cp "$ICON_PNG" "$APPDIR/.DirIcon"
cp "$ICON_PNG" "$APPDIR/usr/share/icons/hicolor/256x256/apps/toolbox.png"

if ! command -v appimagetool >/dev/null 2>&1; then
  echo "appimagetool not found. Install from https://github.com/AppImage/AppImageKit" >&2
  exit 1
fi

mkdir -p "$OUT"
ARCH="$ARCH" appimagetool "$APPDIR" "$APPIMAGE"
rm -rf "$APPDIR"
echo "Created $APPIMAGE"
