#!/usr/bin/env python3
"""Render the walkthrough from the captured fixtures.

    python3 build/build.py --fixtures fixtures --out _site

Three rules govern this file, and they are the same three that govern the
repository it lives in — `ADR-0020` in `clofin-core`:

**Generate, never draw.** Nothing here is a picture of what happened. Every
page is produced from the bundles the capture harness wrote, and the sand
table is laid out from the balance snapshots the scenario captured.

**Replay, never fake.** Every figure on every page is emitted through `cap()`,
which resolves it out of a fixture by JSON pointer and stamps that pointer
into the HTML. `checks/provenance_present.py` walks the built pages and
resolves every one of them again. A value that cannot be resolved cannot be
displayed, because `cap()` raises rather than falling back to a literal.

**Quote, never paraphrase.** Any sentence asserting what a control guarantees
is emitted through `quote_control()` or `quote_invariant()`, which read the
captured `quotations.json` — extracted verbatim from the captured commit's own
`COMPLIANCE.md` and `DOMAIN_MODEL.md` — and render the attribution and the
permalink with it. There is no way to write such a sentence here by hand:
this file contains no control claims, only ids.

Two further things this build refuses to emit, because a check that runs after
the fact is a check somebody can delete:

- **any `<script>`** — the walkthrough computes nothing in a browser, and the
  simplest way to keep that true is to ship no JavaScript at all;
- **any external URL in a `src` or `href` that fetches** — no analytics, no
  fonts, no CDNs. A page about data minimisation that phones home is
  self-refuting. Links to `github.com` are links, not fetches, and are the
  point of the provenance block.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import htmlscan  # noqa: E402
from fixtures import Fixtures, FixtureError, resolve_pointer  # noqa: E402


class BuildRefusal(Exception):
    """The build will not emit this page."""


# ---------------------------------------------------------------------------
# Captured values
# ---------------------------------------------------------------------------

class Renderer:
    """Emits HTML in which every figure carries the pointer it came from."""

    def __init__(self, fixtures: Fixtures):
        self.f = fixtures

    def value(self, source: str, pointer: str):
        return resolve_pointer(self.f.docs[source], pointer)

    def cap(self, source: str, pointer: str, tag: str = "span", cls: str | None = None,
            prefix: str = "", suffix: str = "") -> str:
        """One captured value, with the fixture and pointer it came from.

        `prefix` and `suffix` are outside the marked element, so what the
        check compares is exactly the captured string and nothing around it.
        """
        raw = self.value(source, pointer)
        if raw is None:
            raise BuildRefusal(f"{source}{pointer} resolved to null; a page cannot show it")
        text = raw if isinstance(raw, str) else json.dumps(raw)
        attrs = f' class="{cls}"' if cls else ""
        return (f"{prefix}<{tag}{attrs} data-captured=\"{html.escape(source + '#' + pointer)}\">"
                f"{html.escape(text)}</{tag}>{suffix}")

    def cap_json(self, source: str, pointer: str, label: str = "") -> str:
        """A captured JSON document, pretty-printed.

        Pretty-printing rewraps the bytes and changes no value, and the check
        compares the two documents parsed rather than as text — so a page
        cannot show a body that differs from the captured one in any way that
        matters, and a reader gets something readable. The raw bytes are in
        the fixture, which the site publishes.
        """
        raw = self.value(source, pointer)
        try:
            pretty = json.dumps(json.loads(raw), indent=2)
        except (TypeError, ValueError) as exc:
            raise BuildRefusal(f"{source}{pointer} is not a JSON document: {exc}") from exc
        head = f'<p class="body-label">{html.escape(label)}</p>' if label else ""
        return (f'{head}<pre class="doc" data-captured-json='
                f'"{html.escape(source + "#" + pointer)}">{html.escape(pretty)}</pre>')

    # -- RULE 3 ------------------------------------------------------------

    def quote_control(self, control_id: str, field: str = "statement") -> str:
        control = self.f.control(control_id)
        if field not in control:
            raise BuildRefusal(f"{control_id} has no {field} in the captured quotations")
        index = self.f.quotations["controls"].index(control)
        pointer = f"/controls/{index}/{field}"
        source = self.f.manifest["quotations"]["path"]
        url = control["url"] if field == "statement" else control["boundaryUrl"]
        line = control["line"] if field == "statement" else control["boundaryLine"]
        label = {"statement": "", "boundary": " — boundary of this control"}[field]
        return (
            '<figure class="quote">'
            f'<blockquote>{inline(html.escape(self.value(source, pointer)), source, pointer)}'
            "</blockquote>"
            '<figcaption>'
            f'{html.escape(control["id"])} {html.escape(control["title"])}{html.escape(label)} — '
            f'<a href="{html.escape(url)}"><code>{html.escape(control["file"])}</code> '
            f'line {line}</a>, at the captured commit'
            "</figcaption></figure>")

    def quote_invariant(self, invariant_id: str) -> str:
        invariant = self.f.invariant(invariant_id)
        index = self.f.quotations["invariants"].index(invariant)
        pointer = f"/invariants/{index}/statement"
        source = self.f.manifest["quotations"]["path"]
        return (
            '<figure class="quote">'
            f'<blockquote>{inline(html.escape(self.value(source, pointer)), source, pointer)}'
            "</blockquote>"
            '<figcaption>'
            f'Invariant {html.escape(invariant["id"])} — '
            f'<a href="{html.escape(invariant["url"])}">'
            f'<code>{html.escape(invariant["file"])}</code> line {invariant["line"]}</a>, '
            "at the captured commit"
            "</figcaption></figure>")


CODE_SPAN = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*([^*]+)\*\*")


def inline(escaped: str, source: str, pointer: str) -> str:
    """Markdown code spans and bold, rendered; every other character left alone.

    The quotation is verbatim: this styles the markers the source document
    already contains rather than changing a word. The element still carries
    its pointer, so the check compares the text against the captured string
    with the markers restored.
    """
    styled = CODE_SPAN.sub(lambda m: f"<code>{m.group(1)}</code>", escaped)
    styled = BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", styled)
    return (f'<span data-captured-markdown="{html.escape(source + "#" + pointer)}">'
            f"{styled}</span>")


# ---------------------------------------------------------------------------
# The frame every page carries
# ---------------------------------------------------------------------------

def scope_banner(r: Renderer) -> str:
    """The scope statement and the provenance chips, in-frame and fixed.

    Not a footer, and not dismissible: a screenshot crops a footer, and a
    screenshot of this walkthrough travels as a picture of a payment system
    moving money. The banner is `position: sticky`, so it is in any screenshot
    of any part of any page.

    The provenance values sit together — tag, commit, the tag's recorded
    release-audit coverage, and the captured `identityBinding` —
    because a SHA shown without its coverage invites the reader to supply the
    missing word, and the word they supply is "audited".

    `identityBinding` is labelled by its field name and linked to the ADR
    section that describes the two modes it names, at the captured commit. This
    site does not say what it proves: a sentence of its own would be a
    paraphrase of a control, which RULE 3 does not allow.
    """
    m = "manifest.json"
    return f"""<header class="scope" role="banner">
  <p class="disclaimer" data-scope-statement="disclaimer"
     data-captured="{html.escape('service-info.json#/disclaimer')}">{
        html.escape(r.f.disclaimer())}</p>
  <p class="chips">
    <span class="chip">clofin-core
      {r.cap(m, '/provenance/tag', cls='mono')}</span>
    <span class="chip">{r.cap(m, '/provenance/sourceCommitShort', tag='code')}</span>
    <span class="chip audit">release audit:
      {r.cap(m, '/provenance/releaseAudit/label', cls='mono')}</span>
    <span class="chip"><a href="{html.escape(adr_0027_url(r))}">identityBinding</a>
      {r.cap(m, '/provenance/identityBinding', tag='code')}</span>
  </p>
</header>"""


def provenance_block(r: Renderer) -> str:
    """Everything about where this came from, in one block, all of it captured."""
    m = "manifest.json"
    prov = r.f.provenance()
    commit_url = prov["sourceUrl"]
    return f"""<section class="provenance" id="provenance">
  <h2>Where every figure on this page came from</h2>
  <dl>
    <dt>Repository</dt>
      <dd><a href="https://github.com/EchoJustus/clofin-core">EchoJustus/clofin-core</a></dd>
    <dt>Tag</dt><dd>{r.cap(m, '/provenance/tag', tag='code')}
      ({r.cap(m, '/provenance/tagKind')} tag)</dd>
    <dt>Commit</dt>
      <dd><a href="{html.escape(commit_url)}">{r.cap(m, '/provenance/sourceCommit', tag='code')}</a></dd>
    <dt>Release audit</dt>
      <dd><strong>{r.cap(m, '/provenance/releaseAudit/label')}</strong>
        <blockquote class="coverage">{r.cap(m, '/provenance/releaseAudit/statement')}</blockquote>
        <p class="muted">Read from {r.cap(m, '/provenance/releaseAudit/sourceRef', tag='code')}
          ({r.cap(m, '/provenance/releaseAudit/source')}), digest
          {r.cap(m, '/provenance/releaseAudit/sourceSha256', tag='code')}.</p></dd>
    <dt><code>identityBinding</code></dt>
      <dd>{r.cap(m, '/provenance/identityBinding', tag='code')} —
        <a href="{html.escape(adr_0027_url(r))}">ADR-0027 §3a</a>, at the captured commit</dd>
    <dt>Captured</dt><dd>{r.cap(m, '/provenance/capturedAt', tag='time')}</dd>
    <dt>Schema version of the captured stack</dt>
      <dd>{r.cap(m, '/provenance/schemaVersionApplied', tag='code')}</dd>
    <dt>Capture harness</dt>
      <dd><code>make capture-trace</code> at commit
        {r.cap(m, '/provenance/harness/commit', tag='code')}</dd>
    <dt>Bundle schema</dt><dd>{r.cap(m, '/schemaVersion', tag='code')}</dd>
  </dl>
  <p class="muted">Every value in this block is rendered from
    <a href="fixtures/manifest.json"><code>fixtures/manifest.json</code></a>, not typed.
    <a href="verify.html">How to check any figure on this site</a>.</p>
</section>"""


ADR_0027 = "docs/ADR/0027-browser-clients-cors-allowlist-and-instance-self-identification.md"
ADR_0027_SECTION = "#3a-amendment-2026-09-06--instanceid-and-what-an-echoed-value-establishes"


def adr_0027_url(r: Renderer) -> str:
    """ADR-0027 §3a at the captured commit — the section that describes the
    two modes `identityBinding` names. A link built from the captured
    `sourceUrl`, so it names the commit the fixtures came from rather than
    whatever `main` says today."""
    return (r.f.provenance()["sourceUrl"].replace("/tree/", "/blob/")
            + "/" + ADR_0027 + ADR_0027_SECTION)


# Short navigation labels for the scenarios this build has been taught to
# present. The set of pages is the manifest's, not this table's: a scenario
# the table does not name is still linked, under its captured title.
NAV_LABELS = {
    "segregation-of-duties-refused": "Segregation of duties",
    "settlement-batch-misbehaves": "The settlement batch",
    "evidence-pack-timeline": "The evidence pack",
    "reconciliation-breaks": "Reconciliation",
}


def nav_entries(r: Renderer) -> list[tuple[str, str]]:
    # From the bundles themselves — the same id each page is written under —
    # so a link cannot name a page the build did not write.
    scenarios = [(f"{b['scenario']['id']}.html",
                  NAV_LABELS.get(b["scenario"]["id"], b["scenario"]["title"]))
                 for b in r.f.bundles]
    return ([("index.html", "Overview")] + scenarios
            + [("verify.html", "How to check this")])


def shell(r: Renderer, *, page: str, title: str, body: str) -> str:
    here = ' class="here"'
    nav = "\n".join(
        '      <a href="{}"{}>{}</a>'.format(href, here if href == page else "",
                                             html.escape(label))
        for href, label in nav_entries(r))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — clofin-trace</title>
<meta name="robots" content="index, follow">
<link rel="stylesheet" href="site.css">
</head>
<body>
{scope_banner(r)}
<nav class="nav">
{nav}
</nav>
<main>
{body}
</main>
<footer class="foot">
  <p>A replay walkthrough of
    <a href="https://github.com/EchoJustus/clofin-core">clofin-core</a>. This repository
    contains no CloFin system code and enforces no controls; it presents captured output
    and computes nothing. The scope statement above is served by the system itself and is
    reproduced byte for byte.</p>
</footer>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Scenario rendering
# ---------------------------------------------------------------------------

def step_section(r: Renderer, source: str, index: int, step: dict) -> str:
    p = f"/steps/{index}"
    kind = step.get("kind")
    parts = [f'<section class="step {html.escape(kind)}" id="{html.escape(step["id"])}">']
    parts.append(f'<h3><span class="n">{step.get("n", index + 1)}</span> '
                 f'{r.cap(source, p + "/title")}</h3>')
    if step.get("narrative"):
        # The narrative is captured too — the harness wrote it, in `clofin-core`,
        # beside the call it describes — and it names identifiers in markdown
        # code spans. Rendered through the same inline styler the quotations
        # use, so the marker characters do not appear on the page and the check
        # still compares the text against the captured string.
        parts.append('<p class="narrative">'
                     + inline(html.escape(r.value(source, p + "/narrative")),
                              source, p + "/narrative")
                     + "</p>")

    if kind == "sql":
        parts.append('<p class="body-label">Statement, run directly against the database</p>')
        parts.append(f'<pre class="doc">{html.escape(step["statement"])}</pre>')
        result = step.get("result", {})
        if result.get("ok"):
            parts.append(f'<p class="outcome ok">Applied — '
                         f'{r.cap(source, p + "/result/rows")} row(s).</p>')
        else:
            parts.append('<p class="outcome refused">The database refused it:</p>')
            parts.append(f'<pre class="doc error">{html.escape(result.get("error", ""))}</pre>')
    elif kind in ("http", "balance-snapshot"):
        req = step["request"]
        query = ""
        if req.get("query"):
            query = "?" + "&".join(f"{k}={v}" for k, v in req["query"].items())
        parts.append('<p class="call"><code class="method">'
                     f'{r.cap(source, p + "/request/method")}</code> '
                     f'<code class="path">{r.cap(source, p + "/request/path")}'
                     f'{html.escape(query)}</code></p>')
        actor = (req.get("headers") or {}).get("x-actor-id")
        if actor:
            parts.append(f'<p class="muted">as actor <code>{html.escape(actor)}</code></p>')
        if req.get("bodyRaw"):
            parts.append(r.cap_json(source, p + "/request/bodyRaw", "Request body"))
        status = step["response"]["status"]
        klass = "ok" if status < 400 else "refused"
        parts.append(f'<p class="outcome {klass}">HTTP '
                     f'{r.cap(source, p + "/response/status", cls="status")}</p>')
        if step["response"].get("bodyRaw"):
            parts.append(r.cap_json(source, p + "/response/bodyRaw", "Response body"))
    parts.append("</section>")
    return "\n".join(parts)


def sand_table(r: Renderer, source: str, bundle: dict) -> str:
    table = bundle["sandTable"]
    accounts = table["accounts"]
    head = "".join(f"<th>{html.escape(code)}</th>" for code in accounts)
    rows = []
    note = ""
    for i, row in enumerate(table["rows"]):
        cells = []
        for j, cell in enumerate(row["cells"]):
            pointer = f"/sandTable/rows/{i}/cells/{j}/display"
            cells.append(
                f'<td title="captured by step {html.escape(cell["sourceStep"])}">'
                f'{r.cap(source, pointer, cls="amount")}'
                f'<a class="cell-src" href="#{html.escape(cell["sourceStep"])}">'
                f'step</a></td>')
        klass = ' class="swept"' if row.get("afterStep") == "swept" else ""
        rows.append(f'<tr{klass}><th scope="row">{r.cap(source, f"/sandTable/rows/{i}/label")}'
                    "</th>" + "".join(cells) + "</tr>")
        # Explanatory prose about what the reader is looking at — which row to
        # look at, and which figure in it. Not a claim about what the system
        # guarantees: that is the quoted material above, in the documents' own
        # words. The figure itself is rendered from the cell, not typed.
        if row.get("afterStep") == "swept" and "1300-IN-TRANSIT" in accounts:
            j = accounts.index("1300-IN-TRANSIT")
            note = (
                '<p class="table-note">The highlighted row is the sweep. Its balances are the '
                "same ones the row above shows, and "
                + r.cap(source, f"/sandTable/rows/{i}/cells/{j}/display", cls="amount")
                + " is still sitting in <code>1300-IN-TRANSIT</code> — the payment nobody "
                "answered for. It drains in the row below, when the scheme finally answers.</p>")
    return f"""<section class="sand-table">
  <h2>The ledger sand table</h2>
  <p>Each row is the closing balances of the accounts across the top at one moment, and each
     cell is the <code>closingBalance</code> of a captured
     <code>GET /accounts/&#123;id&#125;/statement</code>
     response — the step it came from is linked inside the cell. Nothing here is added up:
     the balances are the ledger's answers, not this page's.</p>
  <table>
    <thead><tr><th scope="col">After</th>{head}</tr></thead>
    <tbody>
      {"".join(rows)}
    </tbody>
  </table>
  {note}
</section>"""


def journal_section(r: Renderer, source: str, bundle: dict) -> str:
    entries = bundle["journal"]["entries"]
    if not entries:
        return ""
    blocks = []
    for i, entry in enumerate(entries):
        lines = []
        for j, line in enumerate(entry["lines"]):
            lines.append(
                "<tr>"
                f'<td>{r.cap(source, f"/journal/entries/{i}/lines/{j}/line_no")}</td>'
                f'<td>{r.cap(source, f"/journal/entries/{i}/lines/{j}/account_code")}</td>'
                f'<td>{r.cap(source, f"/journal/entries/{i}/lines/{j}/direction")}</td>'
                f'<td class="amount">'
                f'{r.cap(source, f"/journal/entries/{i}/lines/{j}/display")}</td>'
                "</tr>")
        blocks.append(f"""<article class="entry">
  <h3>{r.cap(source, f'/journal/entries/{i}/narrative')}</h3>
  <p class="muted">occurred {r.cap(source, f'/journal/entries/{i}/occurred_at', tag='time')}
     · reference {r.cap(source, f'/journal/entries/{i}/reference_type', tag='code')}
     · entry {r.cap(source, f'/journal/entries/{i}/id', tag='code')}</p>
  <table class="lines">
    <thead><tr><th>#</th><th>Account</th><th>Direction</th><th>Amount</th></tr></thead>
    <tbody>{''.join(lines)}</tbody>
  </table>
</article>""")
    return f"""<section class="journal">
  <h2>Every journal entry this scenario posted</h2>
  <p>Read straight out of the database at the end of the run —
     {r.cap(source, '/journal/entryCount')} entries, with every line of each.</p>
  {''.join(blocks)}
</section>"""


def audit_section(r: Renderer, source: str, bundle: dict) -> str:
    events = bundle["auditEvents"]["events"]
    if not events:
        return ""
    rows = []
    for i, event in enumerate(events):
        rows.append(
            "<tr>"
            f'<td>{r.cap(source, f"/auditEvents/events/{i}/occurred_at", tag="time")}</td>'
            f'<td><code>{r.cap(source, f"/auditEvents/events/{i}/action")}</code></td>'
            f'<td>{r.cap(source, f"/auditEvents/events/{i}/subject_type")}</td>'
            f'<td class="uuid"><code>{r.cap(source, f"/auditEvents/events/{i}/subject_id")}</code></td>'
            f'<td class="uuid"><code>'
            + (r.cap(source, f"/auditEvents/events/{i}/actor_id")
               if event.get("actor_id") else "—")
            + "</code></td></tr>")
    return f"""<section class="audit">
  <h2>Every audit event this scenario produced</h2>
  <p>{r.cap(source, '/auditEvents/count')} events, read from the append-only table itself.
     An event says <em>that</em> something changed and, by digest, what it changed to; it does
     not carry the counterparty name.</p>
  <table>
    <thead><tr><th>Occurred</th><th>Action</th><th>Subject</th><th>Subject id</th>
      <th>Actor</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>"""


def snapshots_appendix(r: Renderer, source: str, bundle: dict, indices: list[int]) -> str:
    if not indices:
        return ""
    rows = []
    for i in indices:
        step = bundle["steps"][i]
        rows.append(
            "<tr>"
            f'<td id="{html.escape(step["id"])}"><code>{html.escape(step["id"])}</code></td>'
            f'<td>{r.cap(source, f"/steps/{i}/account")}</td>'
            f'<td><code>{r.cap(source, f"/steps/{i}/request/path")}</code></td>'
            f'<td class="amount">'
            f'{r.cap(source, f"/steps/{i}/response/body/closingBalance/currency")} '
            f'{r.cap(source, f"/steps/{i}/response/body/closingBalance/minorUnits")}</td>'
            "</tr>")
    return f"""<section class="snapshots">
  <h2>Every balance snapshot, as captured</h2>
  <p>The sand table above is laid out from these. Amounts here are the raw integer count of
     minor units, exactly as the API returned them; the sand table shows the same values with
     the decimal point put in by the system's own formatter, in <code>clofin-core</code>, at
     capture time.</p>
  <table>
    <thead><tr><th>Step</th><th>Account</th><th>Request</th><th>Closing balance</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>"""


SCENARIO_QUOTES = {
    "segregation-of-duties-refused": {
        "intro": (
            "Each attempt is refused. What the refusals mean is not this page's to "
            "say, so the controls say it themselves:"),
        "controls": ["C-01", "C-08", "C-05"],
        "invariants": ["I8", "I9"],
    },
    "settlement-batch-misbehaves": {
        "intro": (
            "The batch survives four kinds of misbehaviour and the journal still balances. "
            "What that guarantees is quoted from the documents the captured commit carries:"),
        "controls": ["C-04", "C-03", "C-05"],
        "invariants": ["I1", "I3", "I11"],
    },
    "evidence-pack-timeline": {
        "intro": (
            "One payment, and the trail it left. What the trail is required to contain:"),
        "controls": ["C-05", "C-09"],
        "invariants": ["I9"],
    },
    "reconciliation-breaks": {
        "intro": (
            "A statement is ingested, delivered again and contradicted, and the breaks the "
            "perturbed statements open are worked through to corrections. What the "
            "controls the acceptance script names, and the invariants beside them, guarantee "
            "is quoted from the documents the captured commit carries:"),
        "controls": ["C-13", "C-06", "C-01", "C-02", "C-03", "C-05", "C-08"],
        "invariants": ["I1", "I3", "I9"],
    },
}


def scenario_page(r: Renderer, bundle_id: str) -> tuple[str, str]:
    source, bundle = r.f.bundle(bundle_id)
    steps = bundle["steps"]
    snapshot_indices = [i for i, s in enumerate(steps) if s.get("kind") == "balance-snapshot"]
    narrative_indices = [i for i, s in enumerate(steps) if s.get("kind") != "balance-snapshot"]

    quotes = SCENARIO_QUOTES.get(bundle_id)
    if quotes is None:
        raise BuildRefusal(
            f"no quotation selection for scenario {bundle_id!r}: its page would show "
            f"refusals and corrections without the controls' own words beside them")
    quoted = "\n".join([r.quote_control(c) for c in quotes["controls"]]
                       + [r.quote_invariant(i) for i in quotes["invariants"]])

    body = [f"""<h1>{r.cap(source, '/scenario/title')}</h1>
<p class="summary">{r.cap(source, '/scenario/summary')}</p>
<p class="muted">Replayed from the acceptance-test script
  <a href="{html.escape(r.f.provenance()['sourceUrl'].replace('/tree/', '/blob/'))
            }/{html.escape(bundle['scenario']['source'])}"><code>{
        html.escape(bundle['scenario']['source'])}</code></a> at the captured commit, against
  organisation <code>{html.escape(bundle['organisation'])}</code> in a database created for
  this run.</p>""",
            provenance_block(r),
            f"""<section class="quotes">
  <h2>What these controls guarantee — in the documents' own words</h2>
  <p>{html.escape(quotes['intro'])}</p>
  {quoted}
  <p class="muted">Each quotation is extracted verbatim from the captured commit's own
     documents by the capture harness, and linked at that commit. Nothing on this page
     restates a control in different words.</p>
</section>"""]

    if bundle.get("sandTable"):
        body.append(sand_table(r, source, bundle))

    body.append('<section class="steps"><h2>What happened, call by call</h2>')
    for i in narrative_indices:
        body.append(step_section(r, source, i, steps[i]))
    body.append("</section>")

    body.append(snapshots_appendix(r, source, bundle, snapshot_indices))
    body.append(journal_section(r, source, bundle))
    body.append(audit_section(r, source, bundle))

    page = f"{bundle_id}.html"
    return page, shell(r, page=page, title=bundle["scenario"]["title"], body="\n".join(body))


# ---------------------------------------------------------------------------
# Index and verification pages
# ---------------------------------------------------------------------------

NUMBER_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]


def scenario_count(r: Renderer) -> str:
    """How many scenarios this capture holds, from the manifest's own list.

    Not typed: "the three scenarios" stayed on the page for a capture that
    holds four, which is the class of figure this site exists to avoid.
    """
    n = len(r.f.manifest["bundles"])
    return NUMBER_WORDS[n] if n < len(NUMBER_WORDS) else str(n)


def index_page(r: Renderer) -> tuple[str, str]:
    cards = []
    for path, bundle in zip(r.f.bundle_paths, r.f.bundles):
        bundle_id = bundle["scenario"]["id"]
        cards.append(f"""<article class="card">
  <h3><a href="{bundle_id}.html">{r.cap(path, '/scenario/title')}</a></h3>
  <p>{r.cap(path, '/scenario/summary')}</p>
  <p class="muted">{r.cap(path, '/auditEvents/count')} audit events ·
     {r.cap(path, '/journal/entryCount')} journal entries</p>
</article>""")

    body = f"""<h1>A replay walkthrough of CloFin</h1>
<p class="lead">CloFin is an open-source reference implementation of an enterprise payments
  and reconciliation core. Its controls are written down and tested, and until now they could
  only be read about. This site shows some of them happening, in {scenario_count(r)} scenarios
  replayed from the project's own acceptance-test scripts.</p>
<p>Everything here is <strong>replayed captured output</strong>. A harness in
  <code>clofin-core</code> started the system at the tagged commit named above, ran the
  {scenario_count(r)} scenarios against it, and wrote down every request, every response,
  every journal entry and every audit event. This site renders those recordings. It has no input, no form, no button
  that submits, and no JavaScript at all: there is nothing here to interact with, because
  everything here already happened.</p>
{provenance_block(r)}
<section class="cards">
  <h2>The {scenario_count(r)} scenarios</h2>
  {''.join(cards)}
</section>
<section>
  <h2>What this site is not</h2>
  <p>It is not a demonstration you can drive, not a console, and not a simulator. It contains
     no CloFin system code, enforces nothing and computes nothing — not a total, not a
     percentage, not a balance. Where you see an amount with a decimal point, that decimal
     point was put in by CloFin's own formatter in <code>clofin-core</code> at capture time,
     beside the integer count of minor units the API actually returned.</p>
  <p>The scope statement at the top of every page is served by the system itself at
     <code>GET /</code> and is reproduced here byte for byte. A check in this repository's CI
     fails the build if it is altered, softened or removed.</p>
</section>"""
    return "index.html", shell(r, page="index.html", title="A replay walkthrough of CloFin",
                               body=body)


def verify_page(r: Renderer) -> tuple[str, str]:
    m = "manifest.json"
    rows = []
    for entry in r.f.manifest["bundles"]:
        rows.append(f"<tr><td><a href=\"fixtures/{html.escape(entry['path'])}\"><code>"
                    f"{html.escape(entry['path'])}</code></a></td>"
                    f"<td><code>{html.escape(entry['sha256'])}</code></td></tr>")
    body = f"""<h1>How to check anything on this site</h1>
<p class="lead">This site asks you to believe one thing: that the figures on it came out of a
  real run of a real system at a commit you can read. Everything below exists so that you do
  not have to take that on trust.</p>
{provenance_block(r)}
<section>
  <h2>1. Every figure names where it came from</h2>
  <p>Every captured value on every page is wrapped in an element carrying a
     <code>data-captured</code> attribute: the fixture it came from and a JSON pointer into it.
     View the source of any page and you can resolve any number on it yourself. A value that
     cannot be resolved cannot be rendered — the build raises rather than falling back to a
     literal.</p>
  <p>Values shown as pretty-printed documents carry <code>data-captured-json</code> instead,
     and are compared with the captured body parsed rather than as text, because the fixture
     holds the raw body the capture recorded and this page rewraps it to be readable.</p>
</section>
<section>
  <h2>2. Two checks run in this repository's CI, and only two</h2>
  <dl>
    <dt><code>provenance-present</code></dt>
    <dd>Every fixture carries a complete stamp, including <code>identityBinding</code>; the
      manifest's digests match the files; a <code>sourceCommit</code> the service reported at
      <code>GET /</code> is the commit the fixtures are stamped with; every page displays the
      tag, the commit, the tag's release-audit coverage and the identity binding together;
      every <code>data-captured</code> figure in the built output resolves to the value it names;
      and no page attaches a word of assurance to the source state without the captured
      coverage label in the same sentence.</dd>
    <dt><code>disclaimer-verbatim</code></dt>
    <dd>The scope statement in the built output — everywhere it appears, and in this
      repository's README — matches the captured <code>GET /</code> response byte for byte.
      Softened wording fails; it does not pass with a warning.</dd>
  </dl>
  <p>There are deliberately no others. A third check here would be a guarantee this repository
     is not entitled to make: <code>clofin-trace</code> owns no truth, and everything it shows
     was produced and checked inside the repository that carries the release-audit scope.</p>
</section>
<section>
  <h2>3. The fixtures themselves</h2>
  <p>Published as they were written, with their digests:</p>
  <table>
    <thead><tr><th>Bundle</th><th>SHA-256</th></tr></thead>
    <tbody>
      <tr><td><a href="fixtures/manifest.json"><code>manifest.json</code></a></td>
        <td><code>the index of everything below</code></td></tr>
      <tr><td><a href="fixtures/service-info.json"><code>service-info.json</code></a></td>
        <td><code>{html.escape(r.f.manifest['fixture']['sha256'])}</code></td></tr>
      <tr><td><a href="fixtures/quotations.json"><code>quotations.json</code></a></td>
        <td><code>{html.escape(r.f.manifest['quotations']['sha256'])}</code></td></tr>
      {''.join(rows)}
    </tbody>
  </table>
</section>
<section>
  <h2>4. The captured GET / response body</h2>
  <p>The captured <code>GET /</code> response body, as the capture fixture records it — the
     scope statement at the top of every page is read from this body.</p>
  {r.cap_json("service-info.json", "/response/bodyRaw", "Response body, GET /")}
</section>
<section>
  <h2>5. The source state, and what its audit did and did not cover</h2>
  <p>The commit these fixtures were captured from is
     <a href="{html.escape(r.f.provenance()['sourceUrl'])}">
     {r.cap(m, '/provenance/sourceCommit', tag='code')}</a>, tagged
     {r.cap(m, '/provenance/tag', tag='code')}. Its release audit reached the coverage quoted in
     the provenance block above and no further, and this site never describes it otherwise.</p>
  <p>The capture harness that produced these fixtures lives in <code>clofin-core</code> and is
     inside that repository's release-audit scope, including a test asserting it cannot emit an
     unstamped bundle. That is the arrangement which lets this repository sit outside audit
     scope without the boundary being a hole.</p>
</section>"""
    return "verify.html", shell(r, page="verify.html", title="How to check this", body=body)


# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------

CSS = """/* Written by build/build.py. No web fonts, no imports, no external requests. */
:root {
  --bg: #fbfbfa; --fg: #1a1a1a; --muted: #5a5a5a; --line: #d9d7d2;
  --panel: #ffffff; --accent: #12506b; --warn: #7a2f1d; --ok: #1f5c33;
  --code-bg: #f2f1ee;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #16171a; --fg: #e8e6e3; --muted: #a2a09c; --line: #33353a;
    --panel: #1d1f23; --accent: #74bcd8; --warn: #e39380; --ok: #7fc79a;
    --code-bg: #24262b;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial,
        sans-serif;
}
code, pre, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
a { color: var(--accent); }
main { max-width: 60rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
h1 { font-size: 1.9rem; line-height: 1.25; margin: 1.5rem 0 .5rem; }
h2 { font-size: 1.3rem; margin: 2.5rem 0 .75rem; padding-top: .75rem;
     border-top: 1px solid var(--line); }
h3 { font-size: 1.05rem; margin: 1.5rem 0 .35rem; }
p { margin: .6rem 0; }
.lead { font-size: 1.08rem; }
.muted { color: var(--muted); font-size: .9rem; }

/* The scope banner: in-frame, sticky, not dismissible. */
.scope {
  position: sticky; top: 0; z-index: 10;
  background: var(--panel); border-bottom: 2px solid var(--accent);
  padding: .55rem 1rem; box-shadow: 0 1px 6px rgba(0,0,0,.08);
}
.scope .disclaimer { margin: 0; font-size: .84rem; line-height: 1.45; font-weight: 600; }
.scope .chips { margin: .3rem 0 0; display: flex; flex-wrap: wrap; gap: .4rem;
                font-size: .78rem; }
.chip { border: 1px solid var(--line); border-radius: 999px; padding: .05rem .55rem;
        color: var(--muted); }
.chip.audit { border-color: var(--warn); color: var(--warn); font-weight: 600; }

.nav { max-width: 60rem; margin: 0 auto; padding: .6rem 1rem 0;
       display: flex; flex-wrap: wrap; gap: .9rem; font-size: .9rem; }
.nav a { text-decoration: none; border-bottom: 2px solid transparent; padding-bottom: .15rem; }
.nav a.here { border-bottom-color: var(--accent); font-weight: 600; }

.provenance { background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
              padding: .9rem 1.1rem; margin: 1.5rem 0; }
.provenance h2 { border: 0; margin: 0 0 .5rem; padding: 0; font-size: 1rem; }
.provenance dl { display: grid; grid-template-columns: minmax(9rem, 15rem) 1fr; gap: .35rem .9rem;
                 margin: 0; font-size: .9rem; }
.provenance dt { color: var(--muted); }
.provenance dd { margin: 0; overflow-wrap: anywhere; }
.coverage { margin: .4rem 0; padding: .4rem .8rem; border-left: 3px solid var(--warn);
            font-size: .88rem; }

.card { border: 1px solid var(--line); border-radius: 8px; padding: .8rem 1rem;
        margin: .8rem 0; background: var(--panel); }
.card h3 { margin-top: 0; }

.quote { margin: 1rem 0; border-left: 3px solid var(--accent); padding: .1rem 0 .1rem 1rem; }
.quote blockquote { margin: 0; font-size: 1rem; }
.quote figcaption { color: var(--muted); font-size: .82rem; margin-top: .3rem; }

.step { border: 1px solid var(--line); border-radius: 8px; padding: .7rem 1rem;
        margin: 1rem 0; background: var(--panel); }
.step h3 { margin-top: .2rem; }
.step .n { display: inline-block; min-width: 1.6rem; color: var(--muted); font-size: .85rem; }
.step.note { border-style: dashed; background: transparent; }
.narrative { margin-top: .2rem; }
.call { margin: .5rem 0 .2rem; }
.method { font-weight: 700; }
.path { overflow-wrap: anywhere; }
.body-label { color: var(--muted); font-size: .8rem; margin: .6rem 0 .2rem;
              text-transform: uppercase; letter-spacing: .04em; }
pre.doc { background: var(--code-bg); border: 1px solid var(--line); border-radius: 6px;
          padding: .6rem .8rem; overflow-x: auto; font-size: .82rem; line-height: 1.45;
          margin: 0; }
pre.doc.error { border-color: var(--warn); }
.outcome { font-weight: 600; margin: .6rem 0 .2rem; }
.outcome.ok { color: var(--ok); }
.outcome.refused { color: var(--warn); }

table { border-collapse: collapse; width: 100%; font-size: .88rem; display: block;
        overflow-x: auto; }
th, td { border: 1px solid var(--line); padding: .35rem .55rem; text-align: left;
         vertical-align: top; }
thead th { background: var(--code-bg); }
td.amount, .amount { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
                     white-space: nowrap; }
tr.swept td, tr.swept th { background: var(--code-bg); box-shadow: inset 3px 0 0 var(--warn); }
.table-note { font-size: .9rem; }
.cell-src { font-size: .7rem; margin-left: .4rem; opacity: .7; }
.uuid code { font-size: .78rem; }
.entry { margin: 1rem 0; }
.entry h3 { font-size: .95rem; }
table.lines { margin-top: .3rem; }

.foot { max-width: 60rem; margin: 0 auto; padding: 1.5rem 1rem 3rem; color: var(--muted);
        font-size: .82rem; border-top: 1px solid var(--line); }
"""


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

FORBIDDEN = [
    (re.compile(r"<script", re.I), "a <script> element: this site computes nothing in a browser"),
    (re.compile(r'\ssrc\s*=\s*"https?://', re.I), "an external resource: static assets only"),
    (re.compile(r'<link[^>]+href\s*=\s*"https?://', re.I),
     "an external stylesheet: static assets only"),
    (re.compile(r"<form", re.I), "a form: there is nothing here to submit"),
    (re.compile(r"<input", re.I), "an input: there is nothing here to type into"),
] + [(pattern, f"{why}: every value on a page must be visible") for pattern, why in htmlscan.HIDING]


def refuse_if_forbidden(page: str, markup: str) -> None:
    for pattern, why in FORBIDDEN:
        if pattern.search(markup):
            raise BuildRefusal(f"{page} contains {why}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", default="fixtures")
    parser.add_argument("--out", default="_site")
    args = parser.parse_args()

    fixtures = Fixtures(Path(args.fixtures))
    problems = fixtures.problems()
    if problems:
        print("build refuses: the fixtures are not usable.", file=sys.stderr)
        for problem in problems:
            print("  -", problem, file=sys.stderr)
        return 1

    r = Renderer(fixtures)
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    pages = [index_page(r)]
    for bundle in fixtures.bundles:
        pages.append(scenario_page(r, bundle["scenario"]["id"]))
    pages.append(verify_page(r))

    for name, markup in pages:
        refuse_if_forbidden(name, markup)
        (out / name).write_text(markup, encoding="utf-8")
        print("wrote", out / name)

    (out / "site.css").write_text(CSS, encoding="utf-8")
    print("wrote", out / "site.css")

    # The fixtures are published beside the pages so that "check it yourself"
    # is an instruction a reader can follow rather than an invitation to trust.
    shutil.copytree(Path(args.fixtures), out / "fixtures")
    print("wrote", out / "fixtures")

    # GitHub Pages runs Jekyll over the artifact unless told not to, and Jekyll
    # would reinterpret the fixtures directory.
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BuildRefusal, FixtureError) as exc:
        print(f"build refuses: {exc}", file=sys.stderr)
        sys.exit(1)
