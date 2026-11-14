#!/usr/bin/env bash
# Build the Linux AppImage from the PyInstaller one-folder bundle.
#
#   packaging/make_appimage.sh <version>
#
# Produces installer/Cytolux-<version>-x86_64.AppImage: one executable file that
# needs no package manager and no root. The user marks it executable and runs it.
# AppImage is chosen over .deb because it works the same on Ubuntu, Fedora, Mint
# and anything else with a reasonably current glibc, and installs nothing.
#
# Running it with --install wires it into the applications menu (see AppRun).

set -euo pipefail

VERSION="${1:?usage: make_appimage.sh <version>}"
ARCH="$(uname -m)"
APPDIR="build/Cytolux.AppDir"
OUT="installer/Cytolux-${VERSION}-${ARCH}.AppImage"

[[ -d dist/Cytolux ]] || { echo "ERROR: dist/Cytolux not found. Run PyInstaller first." >&2; exit 1; }

mkdir -p installer
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps"

echo "Staging the AppDir."
cp -a dist/Cytolux/. "$APPDIR/usr/bin/"
cp cytolux/icons/app/cytolux-256.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/cytolux.png"
cp cytolux/icons/cytolux.svg "$APPDIR/usr/share/icons/hicolor/scalable/apps/cytolux.svg"
cp cytolux/icons/app/cytolux-256.png "$APPDIR/cytolux.png"

cat > "$APPDIR/cytolux.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Version=1.0
Name=Cytolux
GenericName=Flow Cytometry Analysis
Comment=Open FCS files, plot, gate and export statistics
Exec=Cytolux %F
Icon=cytolux
Terminal=false
Categories=Science;Biology;
Keywords=flow;cytometry;FCS;gating;FACS;immunology;
MimeType=application/x-cytolux-workspace;application/vnd.isac.fcs;
StartupNotify=true
StartupWMClass=Cytolux
DESKTOP
cp "$APPDIR/cytolux.desktop" "$APPDIR/usr/share/applications/cytolux.desktop"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/usr/bin/env bash
# AppImage entry point.
#
#   ./Cytolux-*.AppImage             start the application
#   ./Cytolux-*.AppImage --install   add it to the applications menu, then start
#   ./Cytolux-*.AppImage --uninstall remove the menu entry
#
# --install copies nothing: it writes a launcher pointing at wherever this
# AppImage currently sits, so moving the file means running --install again.
set -euo pipefail
HERE="$(dirname "$(readlink -f "${0}")")"

APPIMAGE_PATH="${APPIMAGE:-}"
DESKTOP_FILE="$HOME/.local/share/applications/cytolux.desktop"
ICON_DIR="$HOME/.local/share/icons/hicolor"

case "${1:-}" in
  --install)
    shift
    if [[ -z "$APPIMAGE_PATH" ]]; then
      echo "ERROR: --install only works when running the AppImage itself." >&2
      exit 1
    fi
    mkdir -p "$(dirname "$DESKTOP_FILE")" \
             "$ICON_DIR/256x256/apps" "$ICON_DIR/scalable/apps"
    install -m 644 "$HERE/usr/share/icons/hicolor/256x256/apps/cytolux.png" \
            "$ICON_DIR/256x256/apps/cytolux.png"
    install -m 644 "$HERE/usr/share/icons/hicolor/scalable/apps/cytolux.svg" \
            "$ICON_DIR/scalable/apps/cytolux.svg"
    sed "s|^Exec=.*|Exec=\"$APPIMAGE_PATH\" %F|; s|^Icon=.*|Icon=cytolux|" \
        "$HERE/cytolux.desktop" > "$DESKTOP_FILE"
    chmod 644 "$DESKTOP_FILE"
    command -v update-desktop-database >/dev/null 2>&1 && \
      update-desktop-database "$(dirname "$DESKTOP_FILE")" >/dev/null 2>&1 || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && \
      gtk-update-icon-cache -f -t "$ICON_DIR" >/dev/null 2>&1 || true
    echo "Cytolux added to the applications menu, pointing at $APPIMAGE_PATH"
    ;;
  --uninstall)
    rm -f "$DESKTOP_FILE" "$ICON_DIR/256x256/apps/cytolux.png" \
          "$ICON_DIR/scalable/apps/cytolux.svg"
    command -v update-desktop-database >/dev/null 2>&1 && \
      update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
    echo "Cytolux removed from the applications menu."
    exit 0
    ;;
esac

exec "$HERE/usr/bin/Cytolux" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

echo "Fetching appimagetool."
TOOL="build/appimagetool-${ARCH}.AppImage"
if [[ ! -x "$TOOL" ]]; then
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
  chmod +x "$TOOL"
fi

echo "Building $OUT"
rm -f "$OUT"
# --appimage-extract-and-run: the runner kernel has no FUSE, so the tool cannot
# mount itself the usual way.
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"

chmod +x "$OUT"
ls -lh "$OUT"
