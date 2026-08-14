#!/usr/bin/env python3
"""CHECK 2 of 2 — `disclaimer-verbatim`.

    python3 build/checks/disclaimer_verbatim.py --fixtures fixtures --site _site

The scope statement in the built output must match the captured `GET /`
response **byte for byte**. Not "a disclaimer is present" — that check passes
on softened wording, which is the partial-guard shape standing lesson **L-6**
records. Softened wording must fail, or the check is decoration.

Three rules, and the second is the one with teeth:

1. **Every page carries a marked scope statement**, and every marked scope
   statement equals the captured string exactly. A page with none fails: the
   statement is in-frame and non-dismissible on every page or it is not doing
   its job.

2. **Every near-copy anywhere in the visible text is a full copy.** Wherever a
   page's text contains a distinctive opening of the captured statement, the
   whole captured statement must continue from exactly there. This is what
   catches the failure that matters — not a missing disclaimer, which anyone
   would notice, but a second, friendlier one somewhere further down the page.
   L-6's lesson is that a guard over the copy the author was looking at is the
   defect it exists to catch, so this one looks at every copy it can find.

3. **`README.md` carries it too.** The repository's front door is read more
   often than the site, and it is where the four scope statements were
   required to be from the first commit. Markdown hard-wraps and quotes with
   `>`, so the comparison unwraps line breaks and blockquote markers — and
   nothing else. A changed word still fails.

When a comparison fails, the report names the differing statement and the
exact character at which it diverges, because "the disclaimer differs" is not
a defect report anyone can act on.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import htmlscan  # noqa: E402
from fixtures import Fixtures, FixtureError  # noqa: E402

# Enough of the opening to identify a copy, short enough that a paraphrase of
# the rest is still caught by it.
OPENINGS = ["CloFin operates on synthetic data",
            "It is not connected to any bank",
            "holds no regulatory authorisation",
            "never processes real funds"]


def first_difference(expected: str, actual: str) -> str:
    limit = min(len(expected), len(actual))
    index = next((i for i in range(limit) if expected[i] != actual[i]), limit)
    return (f"      first differs at character {index}:\n"
            f"      captured: …{expected[max(0, index - 30):index + 40]!r}\n"
            f"      rendered: …{actual[max(0, index - 30):index + 40]!r}")


def check_copies(where: str, text: str, captured: str) -> list[str]:
    """Rule 2, over one body of visible text."""
    problems = []
    flat = re.sub(r"\s+", " ", text)
    target = re.sub(r"\s+", " ", captured)
    for opening in OPENINGS:
        start = 0
        while True:
            found = flat.find(opening, start)
            if found < 0:
                break
            start = found + len(opening)
            # Walk back to where the whole captured statement would have begun.
            offset = target.find(opening)
            begin = found - offset
            if begin < 0 or flat[begin:begin + len(target)] != target:
                excerpt = flat[max(0, begin):max(0, begin) + len(target) + 20]
                problems.append(
                    f"{where}: the scope statement appears in a form that is not the captured "
                    f"one, beginning at {opening!r}.\n"
                    f"{first_difference(target, excerpt)}")
                break
    return problems


def unwrap_markdown(text: str) -> str:
    """A markdown blockquote as the paragraph it renders to.

    Blockquote markers and the line breaks the file is hard-wrapped at are
    formatting, not wording. Nothing else is normalised: a changed word, a
    changed punctuation mark or a dropped clause all still fail.
    """
    without_markers = re.sub(r"(?m)^\s*>\s?", "", text)
    return re.sub(r"\s+", " ", without_markers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", default="fixtures")
    parser.add_argument("--site", default="_site")
    parser.add_argument("--readme", default="README.md")
    args = parser.parse_args()

    try:
        fixtures = Fixtures(Path(args.fixtures))
        captured = fixtures.disclaimer()
    except (FixtureError, ValueError, json.JSONDecodeError) as exc:
        print(f"disclaimer-verbatim FAILED: {exc}", file=sys.stderr)
        return 1

    problems: list[str] = []
    pages = sorted(Path(args.site).glob("*.html"))
    if not pages:
        problems.append(f"{args.site}: no pages were built")

    marked_total = 0
    for path in pages:
        page = htmlscan.read(path.read_text(encoding="utf-8"))
        marked = page.by_marker("data-scope-statement")
        if not marked:
            problems.append(f"{path.name}: carries no scope statement. It belongs in-frame on "
                            f"every page, not in a footer on one of them")
        for element in marked:
            marked_total += 1
            if element.text != captured:
                problems.append(
                    f"{path.name}: the rendered scope statement is not the captured one.\n"
                    f"{first_difference(captured, element.text)}")
        problems += check_copies(path.name, page.all_text, captured)

    readme = Path(args.readme)
    if not readme.is_file():
        problems.append(f"{args.readme}: not found; the repository's front door must carry the "
                        f"scope statement too")
    else:
        text = unwrap_markdown(readme.read_text(encoding="utf-8"))
        if re.sub(r"\s+", " ", captured) not in text:
            problems.append(f"{args.readme}: does not carry the captured scope statement "
                            f"verbatim")
        problems += check_copies(args.readme, text, captured)

    if problems:
        print("disclaimer-verbatim FAILED", file=sys.stderr)
        for problem in problems:
            print("  -", problem, file=sys.stderr)
        print(f"\n{len(problems)} problem(s).", file=sys.stderr)
        return 1

    print(f"disclaimer-verbatim OK — the captured GET / scope statement appears verbatim "
          f"{marked_total} time(s) across {len(pages)} page(s), and in {args.readme}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
