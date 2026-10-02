"""A small reader for the built pages, shared by the two checks.

The checks work over the **built output**, not over the templates that made
it: a check that reads the same data the renderer read would only prove the
renderer is self-consistent. So the pages are parsed back with the standard
library and inspected as a reader's browser would see them.

Nothing here is specific to either check — it extracts marked elements, their
ancestry, and the page's visible text, and leaves the judging to the caller.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}

# A sentence never runs across one of these. Recording the boundary matters:
# text joined across two elements can produce a sentence that contains a word
# from its neighbour, and a check asking whether a qualifier is *in the same
# sentence* would then pass on a claim that never carried one.
BLOCK = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
         "td", "th", "tr", "table", "thead", "tbody", "section", "article",
         "header", "footer", "nav", "main", "blockquote", "figure",
         "figcaption", "dl", "dt", "dd", "pre", "br", "title", "aside"}

MARKERS = ("data-captured", "data-captured-json", "data-captured-markdown",
           "data-scope-statement")

# Ways a page can carry text a reader does not see. The site's only styling is
# its stylesheet, so none of these has a use here — and each would let a check
# that asks "is the qualifier beside the claim?" or "is the binding in frame?"
# be answered by something nobody can read. Refused by the build and failed by
# `provenance-present`, over the built output.
HIDING = [
    (re.compile(r"<[a-z][^>]*\shidden(?=[\s=>/])", re.I), "a hidden element"),
    (re.compile(r"<[a-z][^>]*\saria-hidden\s*=", re.I), "an aria-hidden element"),
    (re.compile(r"<[a-z][^>]*\sstyle\s*=", re.I), "an inline style"),
    (re.compile(r"<template[\s>]", re.I), "a template element"),
]


class Marked:
    """One marked element: its attribute, its value, its text and its ancestry."""

    def __init__(self, marker: str, value: str, ancestry: list[str]):
        self.marker = marker
        self.value = value
        self.ancestry = ancestry
        self.text = ""

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<{self.marker}={self.value!r} text={self.text[:40]!r}>"


class PageReader(HTMLParser):
    """Collects marked elements and the page's visible text."""

    def __init__(self, exempt_ancestors: tuple[str, ...] = ()):
        super().__init__(convert_charrefs=True)
        self.exempt_ancestors = exempt_ancestors
        self.stack: list[str] = []
        self.marked: list[Marked] = []
        self.open_marked: list[tuple[Marked, int]] = []
        self.text_parts: list[str] = []
        self.exempt_text_parts: list[str] = []
        # The same visible text as `text_parts`, chunk by chunk, each chunk with
        # the `data-captured` references of the elements it sits inside. Kept
        # so that a check can ask whether a *captured* value — not merely the
        # same word typed — is in a given sentence.
        self.segments: list[tuple[str, tuple[str, ...]]] = []
        self._exempt_depth = 0

    # -- ancestry ----------------------------------------------------------

    def _descriptor(self, tag: str, attrs: dict[str, str]) -> str:
        bits = [tag]
        if attrs.get("id"):
            bits.append("#" + attrs["id"])
        if attrs.get("class"):
            bits.append("." + ".".join(attrs["class"].split()))
        return "".join(bits)

    def handle_starttag(self, tag, attrs):
        attrs = {k: (v or "") for k, v in attrs}
        if tag in BLOCK:
            self._break()
        descriptor = self._descriptor(tag, attrs)
        if tag not in VOID:
            self.stack.append(descriptor)
        exempt_here = any(descriptor.startswith(prefix) or prefix in descriptor
                          for prefix in self.exempt_ancestors)
        if exempt_here and tag not in VOID:
            self._exempt_depth += 1
            self._exempt_marker = len(self.stack)
        for marker in MARKERS:
            if marker in attrs:
                element = Marked(marker, attrs[marker], list(self.stack))
                self.marked.append(element)
                if tag not in VOID:
                    self.open_marked.append((element, len(self.stack)))

    def handle_endtag(self, tag):
        if tag in BLOCK:
            self._break()
        while self.open_marked and self.open_marked[-1][1] > len(self.stack):
            self.open_marked.pop()
        if self.stack:
            if self._exempt_depth and getattr(self, "_exempt_marker", 0) == len(self.stack):
                self._exempt_depth -= 1
            self.stack.pop()
        self.open_marked = [(e, d) for e, d in self.open_marked if d <= len(self.stack)]

    def _break(self):
        if self._exempt_depth:
            self.exempt_text_parts.append("\n")
        else:
            self.text_parts.append("\n")
            self.segments.append(("\n", ()))

    def handle_data(self, data):
        for element, _ in self.open_marked:
            element.text += data
        if "script" in self.stack or "style" in self.stack:
            return
        if self._exempt_depth:
            self.exempt_text_parts.append(data)
        else:
            self.text_parts.append(data)
            self.segments.append((data, tuple(e.value for e, _ in self.open_marked
                                              if e.marker == "data-captured")))

    # -- results -----------------------------------------------------------

    @property
    def text(self) -> str:
        """Visible text outside any exempt region, with block boundaries kept."""
        return re.sub(r"[ \t]+", " ", "".join(self.text_parts))

    @property
    def all_text(self) -> str:
        """Every visible word on the page, exempt regions included."""
        return re.sub(r"[ \t]+", " ", "".join(self.text_parts + self.exempt_text_parts))

    def by_marker(self, marker: str) -> list[Marked]:
        return [m for m in self.marked if m.marker == marker]

    def within(self, element: Marked, ancestor_fragment: str) -> bool:
        return any(ancestor_fragment in a for a in element.ancestry)


def read(markup: str, exempt_ancestors: tuple[str, ...] = ()) -> PageReader:
    reader = PageReader(exempt_ancestors)
    reader.feed(markup)
    reader.close()
    return reader


SENTENCE_END = re.compile(r"(?<=[.!?])[ \t]+|\n+")


def sentences(text: str) -> list[str]:
    """Visible text as sentences.

    Split at sentence-ending punctuation **and** at the block boundaries
    `PageReader` recorded, so that two adjacent elements never become one
    sentence — see `BLOCK`.
    """
    return [re.sub(r"\s+", " ", s).strip()
            for s in SENTENCE_END.split(text) if s.strip()]


def sentences_with_captures(page: PageReader) -> list[tuple[str, set[str]]]:
    """Visible text outside exempt regions as sentences, each with the
    `data-captured` references whose rendered text falls inside it.

    Split exactly as `sentences` splits — at sentence-ending punctuation and at
    the block boundaries `PageReader` recorded — but over the chunks the text
    was built from, so that a sentence knows which captured values it carries.
    This is what lets a check tell a qualifier rendered from a fixture from the
    same word typed by whoever wrote the page.
    """
    text = "".join(chunk for chunk, _ in page.segments)
    spans, at = [], 0
    for chunk, refs in page.segments:
        spans.append((at, at + len(chunk), refs))
        at += len(chunk)
    bounds, start = [], 0
    for match in SENTENCE_END.finditer(text):
        bounds.append((start, match.start()))
        start = match.end()
    bounds.append((start, len(text)))
    found = []
    for begin, end in bounds:
        sentence = re.sub(r"\s+", " ", text[begin:end]).strip()
        if not sentence:
            continue
        refs = set()
        for s0, s1, chunk_refs in spans:
            if chunk_refs and s0 < end and s1 > begin:
                refs.update(chunk_refs)
        found.append((sentence, refs))
    return found
