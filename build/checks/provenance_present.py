#!/usr/bin/env python3
"""CHECK 1 of 2 — `provenance-present`.

    python3 build/checks/provenance_present.py --fixtures fixtures --site _site

Provenance is not one field. It is the whole answer to *where did this figure
come from*, and this check asks that question of four things:

1. **Every fixture carries a complete stamp.** The same field list the capture
   harness enforces before it writes — restated here rather than trusted,
   because this repository is the one outside release-audit scope and its job
   is to check the artifact in front of it. The manifest's digests are
   compared with the files themselves, and every fixture in the set must name
   one source commit.

2. **Every page displays the tag, the commit and the tag's release-audit
   coverage, together and in-frame.** Not in a footer: a screenshot crops a
   footer. All three, together: a SHA shown without its coverage invites the
   reader to supply the missing word, and the word they supply is "audited".

3. **Every figure in the built output resolves.** Each captured value carries
   the fixture and JSON pointer it came from; this check walks the rendered
   HTML and resolves every one of them against the fixture independently of
   the renderer that wrote it. A figure that does not resolve, or that
   resolves to something else, fails the build. That is what makes *replay,
   never fake* mechanical rather than reviewed — including the sand table,
   whose cells are re-read from the steps they name.

4. **No page describes the source state as audited, verified or reviewed
   without the captured coverage qualifier in the same sentence.** `ref-1`'s
   release audit was partial — charter items 1–4 of 8 — and a walkthrough
   implying otherwise would be standing lesson L-14 in the project's most
   public artifact. The provenance block itself is exempt: it is where the
   qualifier lives.

The fourth is here rather than in a third check because the qualifier *is*
provenance. `clofin-trace` runs exactly two checks (ADR-0020), and a third one
would be a guarantee this repository is not entitled to make.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import htmlscan  # noqa: E402
from fixtures import Fixtures, FixtureError, resolve_pointer  # noqa: E402

# Words that characterise the source state. "audit" and "auditor" are not
# here: the trail is called an audit trail, the actor who reads it is an
# auditor, and neither says anything about the state of the source.
CHARACTERISING = re.compile(
    r"\b(audited|verified|reviewed|attested|certified|assured|validated)\b", re.I)

EXEMPT = ("header.scope", "#provenance", "section.provenance")


def resolve(fixtures: Fixtures, reference: str):
    source, _, pointer = reference.partition("#")
    if source not in fixtures.docs:
        raise FixtureError(f"names fixture {source!r}, which is not in the manifest")
    return resolve_pointer(fixtures.docs[source], pointer)


def strip_markdown(text: str) -> str:
    return text.replace("`", "").replace("**", "")


def check_page(fixtures: Fixtures, name: str, markup: str, coverage_label: str) -> list[str]:
    problems: list[str] = []
    page = htmlscan.read(markup, exempt_ancestors=EXEMPT)

    # -- 3. every figure resolves -----------------------------------------
    figures = 0
    for element in page.marked:
        if element.marker == "data-scope-statement":
            continue
        try:
            value = resolve(fixtures, element.value)
        except FixtureError as exc:
            problems.append(f"{name}: a figure {exc}")
            continue
        figures += 1
        if element.marker == "data-captured":
            expected = value if isinstance(value, str) else json.dumps(value)
            if element.text != expected:
                problems.append(
                    f"{name}: the value shown for {element.value} is {element.text!r}, "
                    f"and the fixture holds {expected!r}")
        elif element.marker == "data-captured-json":
            try:
                if json.loads(element.text) != json.loads(value):
                    problems.append(f"{name}: the document shown for {element.value} is not the "
                                    f"captured one")
            except ValueError:
                problems.append(f"{name}: the document shown for {element.value} is not JSON")
        elif element.marker == "data-captured-markdown":
            if strip_markdown(element.text) != strip_markdown(str(value)):
                problems.append(
                    f"{name}: the quotation shown for {element.value} is not the captured text.\n"
                    f"      shown:    {element.text!r}\n"
                    f"      captured: {value!r}")

    if figures == 0:
        problems.append(f"{name}: displays no captured figures at all")

    # -- 2. tag, commit and coverage, together and in-frame ---------------
    banner = [e for e in page.marked
              if e.marker == "data-captured" and page.within(e, "header.scope")]
    shown = {e.value.partition("#")[2] for e in banner}
    for pointer, what in [("/provenance/tag", "the tag"),
                          ("/provenance/sourceCommitShort", "the commit"),
                          ("/provenance/releaseAudit/label", "the release-audit coverage")]:
        if pointer not in shown:
            problems.append(f"{name}: {what} is not in the in-frame provenance banner "
                            f"(expected a captured {pointer})")
    block = [e for e in page.marked
             if e.marker == "data-captured" and page.within(e, "#provenance")]
    block_shown = {e.value.partition("#")[2] for e in block}
    for pointer, what in [("/provenance/sourceCommit", "the full commit SHA"),
                          ("/provenance/releaseAudit/statement",
                           "the verbatim release-audit coverage")]:
        if pointer not in block_shown:
            problems.append(f"{name}: {what} is not in the provenance block "
                            f"(expected a captured {pointer})")

    # -- 4. no unqualified claim about the source state -------------------
    for sentence in htmlscan.sentences(page.text):
        hit = CHARACTERISING.search(sentence)
        if hit and coverage_label.lower() not in sentence.lower():
            problems.append(
                f"{name}: a sentence calls the source state {hit.group(0)!r} without the "
                f"captured coverage qualifier ({coverage_label!r}) beside it:\n"
                f"      {sentence}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", default="fixtures")
    parser.add_argument("--site", default="_site")
    args = parser.parse_args()

    try:
        fixtures = Fixtures(Path(args.fixtures))
        problems = list(fixtures.problems())
        coverage_label = fixtures.provenance()["releaseAudit"]["label"]
    except (FixtureError, ValueError, KeyError, TypeError) as exc:
        # A malformed fixture is a failure, not a traceback. The whole value of
        # this check is that the report says what to fix.
        print(f"provenance-present FAILED: the fixtures could not be read: {exc}",
              file=sys.stderr)
        return 1

    pages = sorted(Path(args.site).glob("*.html"))
    if not pages:
        problems.append(f"{args.site}: no pages were built")
    for page in pages:
        problems += check_page(fixtures, page.name, page.read_text(encoding="utf-8"),
                               coverage_label)

    if problems:
        print("provenance-present FAILED", file=sys.stderr)
        for problem in problems:
            print("  -", problem, file=sys.stderr)
        print(f"\n{len(problems)} problem(s).", file=sys.stderr)
        return 1

    prov = fixtures.provenance()
    print(f"provenance-present OK — {len(pages)} page(s) and "
          f"{len(fixtures.bundles) + 2} fixture(s), all stamped "
          f"{prov['tag']} {prov['sourceCommitShort']}, release audit: {coverage_label}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
