"""The built-in "how do I…" search.

No network, no model, no API key: it ranks the help corpus in help_text.py
against the words you type. Deliberately headless, like the engine, so the
answer quality can be tested without starting a GUI.

Ranking is TF-IDF-ish over a small corpus, with three adjustments that matter
more than the maths at this size:
  - a synonym table, so "spreadsheet" finds the Excel export;
  - weighting a document's own keywords above its prose;
  - a prefix match, so half-typed words still rank.
"""
import math
import re
from collections import defaultdict

from .help_text import MENU_TIPS, SHORTCUTS, TAB_TIPS, TOPICS

# Words the user types on the left, words the corpus uses on the right.
SYNONYMS = {
    "xlsx": "excel", "spreadsheet": "excel", "csv": "excel",
    "wsp": "flowjo", "fj": "flowjo",
    "comp": "compensation", "spillover": "compensation", "unmix": "compensation",
    "compensate": "compensation", "compensated": "compensation",
    "pop": "population", "pops": "population", "populations": "population",
    "freq": "frequency", "pct": "percent", "percentage": "percent", "%": "percent",
    "mfi": "median", "geomean": "geometric",
    "biexp": "biex", "biexponential": "biex", "logicle": "biex",
    "fcs": "sample", "samples": "sample", "tube": "sample", "tubes": "sample",
    "well": "sample", "wells": "sample", "plate": "sample",
    "gates": "gate", "gating": "gate", "draw": "gate",
    "template": "template", "templates": "template",
    "marker": "channel", "markers": "channel", "channels": "channel",
    "detector": "channel", "parameter": "channel", "fluorochrome": "channel",
    "shortcut": "key", "shortcuts": "key", "hotkey": "key", "keyboard": "key",
    "save": "save", "saving": "save", "saved": "save",
    "open": "open", "opening": "open", "load": "open", "loading": "open",
    "import": "import", "importing": "import",
    "export": "export", "exporting": "export", "write": "export",
    "rename": "rename", "renaming": "rename",
    "delete": "delete", "remove": "delete", "deleting": "delete",
    "negative": "negative", "negatives": "negative",
    "axis": "axis", "axes": "axis", "scale": "axis", "scaling": "axis",
}

STOP = {
    "a", "an", "the", "is", "are", "was", "were", "be", "to", "of", "in", "on",
    "for", "and", "or", "it", "this", "that", "with", "as", "at", "by", "from",
    "how", "do", "i", "can", "my", "me", "you", "your", "what", "where", "which",
    "when", "why", "if", "not", "no", "does", "did", "get", "want", "need",
    "please", "help", "there", "then", "them", "they", "use", "using", "make",
}

_WORD = re.compile(r"[a-z0-9%+\-]+")


def normalise(text):
    """Lowercase, split into words, drop stopwords, apply synonyms, light stemming."""
    out = []
    for w in _WORD.findall(text.lower()):
        w = SYNONYMS.get(w, w)
        if w in STOP or len(w) < 2:
            continue
        if w not in SYNONYMS.values():
            if w.endswith("ies") and len(w) > 4:
                w = w[:-3] + "y"
            elif w.endswith("es") and len(w) > 4:
                w = w[:-2]
            elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
                w = w[:-1]
        out.append(w)
    return out


class Answer:
    """One result: what to do, and where the control lives."""

    def __init__(self, title, body, where=None, score=0.0):
        self.title = title
        self.body = body
        self.where = where      # e.g. "File > Export statistics to Excel…"
        self.score = score

    def __repr__(self):
        return "Answer(%r, score=%.2f)" % (self.title, self.score)


def _documents():
    """Build the searchable corpus once, from the same text the tooltips use."""
    docs = []
    for keys, answer in TOPICS:
        docs.append(Answer(keys.split(",")[0].strip().capitalize(), answer))
        docs[-1]._keywords = keys
    for text, tip in MENU_TIPS.items():
        menu = _menu_of(text)
        a = Answer(text.rstrip("…"), tip, where="%s > %s" % (menu, text) if menu else text)
        a._keywords = text
        docs.append(a)
    for what, keys in SHORTCUTS.items():
        a = Answer("%s: %s" % (what, keys),
                   "The keyboard shortcut for %s is %s." % (what[0].lower() + what[1:], keys),
                   where="keyboard")
        a._keywords = "shortcut key " + what
        docs.append(a)
    for tab, tip in TAB_TIPS.items():
        a = Answer("%s tab" % tab, tip, where="the %s tab" % tab)
        a._keywords = tab
        docs.append(a)
    return docs


_FILE = {"Open FCS folder…", "Add FCS files…", "Open workspace…", "Save workspace",
         "Save workspace as…", "Import FlowJo workspace (.wsp)…", "Save gating template…",
         "Apply gating template to these samples…",
         "New analysis: FCS folder + gating template…",
         "Export statistics to Excel…", "Export plot as image…", "Quit"}
_COMP = {"Use the matrix stored in the files (FlowJo: acquisition-defined)", "No compensation",
         "Load matrix from CSV…", "View / edit matrix…"}
_EDIT = {"Rename channels (marker names)…", "Delete selected gate",
         "Annotate samples (donor, dose…)…", "Add statistic…"}
_HELP = {"Quick guide", "Check against FlowJo counts"}


def _menu_of(text):
    for name, members in (("File", _FILE), ("Compensation", _COMP),
                          ("Edit", _EDIT), ("Help", _HELP)):
        if text in members:
            return name
    return None


class Assistant:
    """Ranks the help corpus against a plain-language question."""

    KEYWORD_WEIGHT = 2.5

    def __init__(self, docs=None):
        self.docs = docs if docs is not None else _documents()
        self._tokens = []
        df = defaultdict(int)
        for d in self.docs:
            body = normalise(d.title + " " + d.body)
            keys = normalise(getattr(d, "_keywords", ""))
            self._tokens.append((set(body), set(keys), body + keys))
            for t in set(body) | set(keys):
                df[t] += 1
        n = max(1, len(self.docs))
        self._idf = {t: math.log(1 + n / c) for t, c in df.items()}

    def _score(self, query_tokens, i):
        body, keys, all_tokens = self._tokens[i]
        score = 0.0
        for q in query_tokens:
            w = self._idf.get(q)
            if w is None:
                # unseen word: allow a prefix match so half-typed words still rank
                hits = [t for t in all_tokens if t.startswith(q) and len(q) >= 3]
                if hits:
                    score += 0.5 * self._idf.get(hits[0], 1.0)
                continue
            if q in keys:
                score += w * self.KEYWORD_WEIGHT
            elif q in body:
                score += w
        return score

    def ask(self, question, limit=3, threshold=0.6):
        """Best answers for a question, highest score first. Empty if nothing is close."""
        q = normalise(question or "")
        if not q:
            return []
        scored = []
        for i, d in enumerate(self.docs):
            s = self._score(q, i)
            if s >= threshold:
                scored.append(Answer(d.title, d.body, d.where, s))
        scored.sort(key=lambda a: -a.score)
        return scored[:limit]

    def suggestions(self):
        """Example questions, shown before the user types anything."""
        return [k.split(",")[0].strip() for k, _ in TOPICS[:6]]


NO_MATCH = ("I do not have an answer for that. Press F1 for the quick guide, which covers the "
            "whole workflow, or try naming the thing you are looking for: a gate, a channel, "
            "compensation, a template, or the Excel export.")
