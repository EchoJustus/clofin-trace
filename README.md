# clofin-trace

A replay walkthrough of [CloFin](https://github.com/EchoJustus/clofin-core) —
an open-source, synthetic-data reference implementation of an enterprise
payments and reconciliation core.

**This repository contains no CloFin system code and enforces no controls.**
It presents captured output; it computes nothing.

The built walkthrough is served at <https://echojustus.github.io/clofin-trace/>.

## What this site shows

Every figure on this site is **replayed captured output** of
[`clofin-core` at tag `ref-2`, commit `32dfcc9`](https://github.com/EchoJustus/clofin-core/tree/32dfcc99025fa339478f7ecf91b42ded71d725c2).
If a value cannot be traced to captured output of that commit, it does not
appear ([ADR-0020](https://github.com/EchoJustus/clofin-core/blob/main/docs/ADR/0020-two-repositories-and-the-generate-replay-rules.md),
RULE 2 — replay, never fake).

Four scenarios, captured by `make capture-trace` in `clofin-core`:

| | |
|---|---|
| **Segregation of duties, attempted and refused** | An operator tries to open a ledger account, a second operator tries to submit somebody else's draft, and the maker tries to approve her own payment |
| **A settlement batch, and the four ways a scheme misbehaves** | Partial failure, a duplicate answer, a contradiction and a silence — with the ledger sand table following the money through `1100-CLIENT-FUNDS` → `1300-IN-TRANSIT` → `2100-CLIENT-PAYABLE` |
| **The evidence pack an auditor extracts** | One payment from capture to settlement, then its complete trail |
| **Reconciliation: a statement, its breaks, and the corrections that close them** | A simulated scheme statement ingested, delivered again and contradicted; the breaks the perturbed statements open, queued, assigned and corrected — one correction refused — and a returned payment retried, with a sand table over the settlement accounts and `2200-UNAPPLIED` |

`ref-2`'s release-audit coverage, as its annotated tag records it and as the
capture harness stamps it into every fixture, is labelled **`COMPLETE`**. The
coverage is not written down here beyond that label: the harness reads the
whole `RELEASE AUDIT:` paragraph from the tag's own annotation and every page
renders it, verbatim, beside the tag and the commit — so the walkthrough shows
whatever the tag actually records, and never characterises its source without
that captured qualifier.

Every fixture also carries **`identityBinding`**. Each page shows its captured
value next to the tag, the commit and the coverage, linked to
[ADR-0027 §3a](https://github.com/EchoJustus/clofin-core/blob/32dfcc99025fa339478f7ecf91b42ded71d725c2/docs/ADR/0027-browser-clients-cors-allowlist-and-instance-self-identification.md)
at the captured commit, which describes the two modes.

## Scope

Quoted verbatim from the system's own `GET /` response:

> CloFin operates on synthetic data only. It is not connected to any bank,
> payment scheme or central bank, holds no regulatory authorisation, and
> never processes real funds.

Those words are captured as a fixture, rendered in-frame and non-dismissible on
every page of the site, and compared byte for byte by CI — here in this README
too. Softened wording fails the build.

## Building it

No dependencies. Python 3.11 or later, standard library only:

```sh
python3 build/build.py --fixtures fixtures --out _site
python3 build/checks/provenance_present.py  --fixtures fixtures --site _site
python3 build/checks/disclaimer_verbatim.py --fixtures fixtures --site _site
```

Then open `_site/index.html`. The published site is the same output, built by
[`.github/workflows/pages.yml`](.github/workflows/pages.yml).

## The two checks, and why there are only two

| Check | What it fails on |
|---|---|
| **`provenance-present`** | A manifest of any bundle schema but `clofin.capture/2`, named; a fixture missing any part of its stamp, `identityBinding` included; a manifest digest that no longer matches its file; a captured `GET /` whose self-reported `sourceCommit` is not the commit the fixtures are stamped with; a page that does not show the tag, the commit, the tag's release-audit coverage and the identity binding together and in-frame; a displayed figure that does not resolve to the captured value it names; a sand-table cell that no longer equals the step it was read from; a sentence that attaches a word of assurance to the source state without the captured coverage label beside it |
| **`disclaimer-verbatim`** | Any rendering of the scope statement — on any page, or in this README — that is not the captured `GET /` response byte for byte, including a softened or shortened one |

A third check here would be a guarantee this repository is not entitled to
make. Everything it displays was produced by the capture harness in
`clofin-core`, which is inside that repository's release-audit scope and
carries a test asserting it cannot emit an unstamped bundle. That is the
arrangement which lets this repository sit outside audit scope without the
boundary being a hole.

## What is deliberately absent

No input, no form, no button that submits, no analytics, no telemetry, no
cookies, no third-party fonts or CDNs, and **no JavaScript at all**. There is
nothing here to interact with, because everything here already happened. The
build refuses to emit a page containing any of them.

## Fixtures

`fixtures/` holds the output of **one capture run — one capture per site**,
published with the site so that any figure can be checked. The build reads one
bundle schema and refuses a manifest of any other, naming its version. The
previous capture, of `ref-1` (`5c7b4ba`, schema `clofin.capture/1`), is not
rebuilt here; it lives in this repository's history at commit
[`bc0017c`](https://github.com/EchoJustus/clofin-trace/tree/bc0017c/fixtures).

| File | |
|---|---|
| `manifest.json` | The index, with a digest for every other file |
| `service-info.json` | The captured `GET /` response — the scope statement, byte for byte |
| `quotations.json` | Control statements and invariants, extracted verbatim from the captured commit's own `COMPLIANCE.md` and `DOMAIN_MODEL.md` |
| `bundles/*.json` | One per scenario: every request and response, every journal entry and line, every audit event |

## Licence

Eclipse Public License 2.0 — see [LICENSE](LICENSE), matching `clofin-core`.
