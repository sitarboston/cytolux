"""Answer quality for the built-in help search.

These are the spec: each case is a question a confused user would actually
type, paired with the answer they should get first. Tuning the ranking is
only allowed to make these greener.
"""
import pytest

from cytolux.assistant import NO_MATCH, Assistant, normalise

ASK = [
    ("how do I export to excel",                      "excel"),
    ("spreadsheet",                                   "excel"),
    ("get the numbers out",                           "excel"),
    ("open my flowjo gates",                          "flowjo"),
    ("import a wsp file",                             "flowjo"),
    ("reuse the same gates on a new run",             "template"),
    ("diagonal smear between two colours",            "compensation"),
    ("how do I compensate",                           "compensation"),
    ("spillover matrix",                              "compensation"),
    ("change the gate on just one sample",            "sample only"),
    ("my events pile up at the edge of the axis",     "negative"),
    ("axis says Comp-V710-A instead of CD3",          "rename"),
    ("add donor and dose to my samples",              "annotate"),
    ("see all my samples at once",                    "all samples"),
    ("what is the shortcut to save",                  "ctrl+s"),
    ("shortcut for adding a statistic",               "ctrl+t"),
    ("how do I draw a polygon",                       "polygon"),
    ("my gate counts zero everywhere",                "zero"),
    ("where do I put the positive cutoff",            "fmo"),
]


@pytest.fixture(scope="module")
def a():
    return Assistant()


@pytest.mark.parametrize("question,expect", ASK, ids=[q for q, _ in ASK])
def test_top_answer_is_relevant(a, question, expect):
    hits = a.ask(question)
    assert hits, "no answer at all for %r" % question
    blob = " ".join((h.title + " " + h.body + " " + (h.where or "")) for h in hits[:2]).lower()
    assert expect in blob, (
        "expected %r in the top answers for %r, got %s"
        % (expect, question, [h.title for h in hits]))


def test_nonsense_returns_nothing_rather_than_a_wrong_answer(a):
    """Confidently wrong is worse than 'I don't know'."""
    for junk in ("zxcvbnm", "what is the capital of France", "qqqq wwww"):
        assert a.ask(junk) == [], "should not have answered %r" % junk


def test_empty_question_is_not_an_error(a):
    assert a.ask("") == []
    assert a.ask(None) == []


def test_results_are_ordered_by_score(a):
    hits = a.ask("export statistics to excel", limit=5)
    assert len(hits) >= 2
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_limit_is_respected(a):
    assert len(a.ask("gate", limit=2)) <= 2


def test_menu_answers_say_where_the_control_is(a):
    hits = a.ask("export statistics to excel", limit=5)
    located = [h for h in hits if h.where and ">" in h.where]
    assert located, "at least one answer should name the menu path"
    assert located[0].where.startswith("File > ")


def test_half_typed_words_still_find_something(a):
    assert a.ask("compens"), "prefix match should rescue a half-typed word"


def test_suggestions_are_offered_before_typing(a):
    s = a.suggestions()
    assert 3 <= len(s) <= 8 and all(isinstance(x, str) and x for x in s)


def test_no_match_message_points_somewhere_useful():
    assert "F1" in NO_MATCH


def test_normalise_drops_stopwords_and_applies_synonyms():
    assert "excel" in normalise("export to a spreadsheet")
    assert "flowjo" in normalise("open the wsp")
    assert "the" not in normalise("the gate")


def test_the_assistant_never_touches_the_network():
    """Offline by construction: no socket, no http client, no api key."""
    import inspect
    from cytolux import assistant
    src = inspect.getsource(assistant)
    for bad in ("socket", "requests", "urllib", "httpx", "anthropic", "openai", "api_key", "http"):
        assert bad not in src.lower(), "assistant must stay offline, found %r" % bad
