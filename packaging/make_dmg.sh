#!/usr/bin/env bash
# Build the macOS disk image from the PyInstaller .app bundle.
#
#   packaging/make_dmg.sh <version>
#
# Produces installer/Cytolux-<version>-macos-<arch>.dmg: a window holding the app
# and a shortcut to /Applications, which is how a Mac user installs it.
#
# The bundle is ad-hoc signed. That is not notarization: on first launch macOS
# will still say the developer cannot be verified, and the user opens it from the
# right-click menu once. Without ad-hoc signing an arm64 bundle is killed outright
# rather than merely warned about, so this step is not cosmetic.

set -euo pipefail

VERSION="${1:?usage: make_dmg.sh <version>}"
ARCH="$(uname -m)"
APP="dist/Cytolux.app"
STAGE="$(mktemp -d)"
OUT="installer/Cytolux-${VERSION}-macos-${ARCH}.dmg"

[[ -d "$APP" ]] || { echo "ERROR: $APP not found. Run PyInstaller first." >&2; exit 1; }

mkdir -p installer

# The Windows installer registers .fgw and .fcs so a double-click opens Cytolux.
# The .app had no document types at all, so the same double-click on a Mac did
# nothing. Declared here rather than in the PyInstaller command line, because
# PyInstaller has no flag for document types, and before codesign, because editing
# anything inside the bundle after signing invalidates the signature.
echo "Declaring the document types Cytolux opens."
python3 - "$APP/Contents/Info.plist" <<'PLIST'
import plistlib, sys

path = sys.argv[1]
with open(path, "rb") as fh:
    pl = plistlib.load(fh)

pl["CFBundleDocumentTypes"] = [
    {
        "CFBundleTypeName": "Cytolux workspace",
        "CFBundleTypeExtensions": ["fgw"],
        "CFBundleTypeRole": "Editor",
        "LSHandlerRank": "Owner",
    },
    {
        "CFBundleTypeName": "Flow cytometry standard data",
        "CFBundleTypeExtensions": ["fcs", "FCS"],
        "CFBundleTypeRole": "Viewer",
        # Alternate, not Owner: a Mac with FlowJo or FCS Express on it should keep
        # whatever the user already chose for .fcs.
        "LSHandlerRank": "Alternate",
    },
]
# Qt reads this to decide whether the window can go full screen properly, and a
# bundle without it is treated as a pre-retina application on some displays.
pl["NSHighResolutionCapable"] = True
pl.setdefault("NSRequiresAquaSystemAppearance", False)

with open(path, "wb") as fh:
    plistlib.dump(pl, fh)
print("  CFBundleDocumentTypes written for .fgw and .fcs")
PLIST

echo "Ad-hoc signing the bundle."
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP" && echo "  signature verifies"

echo "Staging the disk image contents."
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

echo "Building $OUT"
rm -f "$OUT"
hdiutil create \
    -volname "Cytolux $VERSION" \
    -srcfolder "$STAGE" \
    -fs HFS+ \
    -format UDZO \
    -imagekey zlib-level=9 \
    -ov "$OUT"

rm -rf "$STAGE"
ls -lh "$OUT"
