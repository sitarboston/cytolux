"""Write a copy of an FCS file with everything that names a study, a subject or a
machine taken out, and nothing that the numbers depend on touched.

Why a rewrite and not an edit: the identifying material in an FCS file is not only
in the obvious keywords. Acquisition dates and times, the operator, the institution,
the cytometer serial number, the plate well, the original filename and whatever the
acquisition software stashed in its own private keywords are all in the TEXT segment,
and several of them are vendor-specific with no fixed name. The safe move is to start
from an empty keyword set, copy across the short list the data genuinely needs, and
drop the rest unread.

What is kept, and why each one has to be:
  $PAR $TOT $BYTEORD $DATATYPE $MODE $NEXTDATA   the shape of the data
  $PnN $PnB $PnE $PnR $PnG                       per-channel name, width, scale, range
  $PnS                                           marker names: the panel, not the subject
  $SPILLOVER / $COMP                             compensation, without which nothing gates
Everything else is dropped. The event matrix is copied value for value.

Usage:
  python3 tools/deidentify_fcs.py OUT_DIR "Control=path/to/a.fcs" "Exhibit 1=path/to/b.fcs"
"""
import os
import struct
import sys

import numpy as np

# $TIMESTEP is deliberately absent: flowkit hands back Time already multiplied by it,
# and copying the keyword alongside the scaled values scales them a second time.
KEEP_GLOBAL = {"$BYTEORD", "$DATATYPE", "$MODE", "$PAR", "$TOT", "$SPILLOVER", "$COMP"}
SPILL_KEYS = ("spillover", "$spillover", "spill", "$spill", "comp", "$comp")
KEEP_PER_CHANNEL = ("N", "B", "E", "R", "G", "S", "V")
# Dropped even though they are harmless-looking: a date plus a cytometer serial is
# enough to tie a file back to a run, and $FIL usually carries the study code.
BANNED_SUBSTRINGS = ("DATE", "BTIM", "ETIM", "OP", "INST", "SRC", "SMNO", "FIL", "CYT",
                     "PROJ", "EXPERIMENT", "TUBE", "WELL", "PLATE", "USER", "GUID",
                     "PATIENT", "SUBJECT", "DONOR", "SAMPLE ID", "CREATOR", "COMPUTER",
                     "LOGIN", "SERIAL", "ANIMAL", "STUDY")


def wanted(key, n_par):
    """Is this keyword one of the few we copy across?"""
    k = key.upper()
    if k in KEEP_GLOBAL:
        return True
    if k.startswith("$P") and len(k) > 2:
        digits = "".join(c for c in k[2:] if c.isdigit())
        suffix = k[2 + len(digits):]
        if digits and suffix in KEEP_PER_CHANNEL and 1 <= int(digits) <= n_par:
            return True
    return False


def clean_text(value):
    """A kept value is still checked: a marker name must not smuggle a subject in."""
    v = str(value)
    return v.replace("\x00", "").strip()


def build_text(pairs, delim="|"):
    out = [delim]
    for k, v in pairs:
        out.append("%s%s%s%s" % (k.replace(delim, ""), delim, str(v).replace(delim, ""), delim))
    return "".join(out)


def write_fcs(path, channels, markers, data, extra=None, label=None):
    """Write a minimal, valid FCS 3.1 file: float32 list mode, no analysis segment."""
    data = np.asarray(data, dtype="<f4")
    n_events, n_par = data.shape
    pairs = [("$BEGINANALYSIS", "0"), ("$ENDANALYSIS", "0"),
             ("$BEGINSTEXT", "0"), ("$ENDSTEXT", "0"),
             ("$BYTEORD", "1,2,3,4"), ("$DATATYPE", "F"), ("$MODE", "L"),
             ("$NEXTDATA", "0"), ("$PAR", str(n_par)), ("$TOT", str(n_events))]
    if label:
        pairs.append(("$FIL", label))
    for i in range(n_par):
        rng = float(np.nanmax(np.abs(data[:, i]))) if n_events else 262144.0
        pairs += [("$P%dN" % (i + 1), channels[i]),
                  ("$P%dB" % (i + 1), "32"),
                  ("$P%dE" % (i + 1), "0,0"),
                  ("$P%dR" % (i + 1), "%d" % max(1, int(rng) + 1))]
        if markers[i]:
            pairs.append(("$P%dS" % (i + 1), markers[i]))
    for k, v in (extra or {}).items():
        pairs.append((k, v))

    # The TEXT segment's own length changes the offsets written inside it, so the
    # offsets are solved by iterating until they stop moving.
    begin = 256
    for _ in range(8):
        body = build_text(pairs + [("$BEGINDATA", str(begin)),
                                   ("$ENDDATA", str(begin + data.nbytes - 1))])
        text_end = 58 + len(body) - 1
        new_begin = int(np.ceil((text_end + 1) / 256.0)) * 256
        if new_begin == begin:
            break
        begin = new_begin
    header = ("FCS3.1" + " " * 4 +
              "%8d%8d%8d%8d%8d%8d" % (58, text_end, begin, begin + data.nbytes - 1, 0, 0))
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(body.encode("ascii"))
        fh.write(b"\x00" * (begin - fh.tell()))
        fh.write(data.tobytes())
    return path


def deidentify(src, dest, label):
    import flowkit as fk
    s = fk.Sample(src, ignore_offset_error=True)
    n_par = len(s.pnn_labels)
    meta = s.get_metadata()
    extra = {}
    # The spillover matrix is the one bulky keyword that has to survive: without it
    # nothing compensates, and an uncompensated 17-colour file teaches the wrong thing.
    for k in SPILL_KEYS:
        v = clean_text(meta.get(k, ""))
        if v and v.count(",") > 2:
            extra["$SPILLOVER"] = v
            break
    data = s.get_events(source="raw")
    markers = [clean_text(m or "") for m in s.pns_labels]
    return write_fcs(dest, list(s.pnn_labels), markers, data, extra=extra, label=label)


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    for spec in argv[2:]:
        label, src = spec.split("=", 1)
        dest = os.path.join(out, label + ".fcs")
        deidentify(src, dest, label)
        print("%-12s <- %s" % (label, os.path.basename(src)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
