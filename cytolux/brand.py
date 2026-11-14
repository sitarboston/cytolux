"""Who made this, in one place.

The attribution is not decoration and it is not a setting. It is in the window
where the work happens, in the About box, and inside every file the program
writes, so a figure or a workbook that travels on its own still says where it
came from.

What it deliberately does not do is stamp a visible watermark across an exported
plot. A figure with a name written over the data is a figure no journal will take
and no reviewer will trust, which would make the attribution cost its author the
very credit it was meant to give. The name rides in the file's metadata instead,
where it survives copying and never touches the picture.
"""
from . import __version__

APP = "Cytolux"
CREATOR = "Samyabrata Bhaduri, PhD"
YEAR = "2026"
COPYRIGHT = "© %s %s" % (YEAR, CREATOR)
TAGLINE = "Flow cytometry gating, with the uncertainty shown"

CREDIT = "%s · created by %s" % (APP, CREATOR)
LONG_CREDIT = "%s %s · created by %s · %s" % (APP, __version__, CREATOR, COPYRIGHT)


def software_tag():
    """The one-line stamp written into exported files."""
    return "%s %s (created by %s)" % (APP, __version__, CREATOR)


def png_metadata():
    """Text fields PNG carries natively, read by ImageMagick, exiftool and Explorer."""
    return {
        "Software": software_tag(),
        "Author": CREATOR,
        "Copyright": COPYRIGHT,
        "Description": "Figure exported from %s" % APP,
    }
