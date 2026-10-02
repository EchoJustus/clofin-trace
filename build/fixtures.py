"""Reading the captured fixtures, and refusing to read anything else.

`clofin-trace` owns no truth. Every value it displays comes out of a bundle
written by the capture harness in `clofin-core`, and this module is the only
door those values come through: the build resolves each figure by JSON pointer
and stamps the pointer into the page, so the check in `checks/` can walk the
built HTML and resolve every one of them again, independently.

Nothing here computes. There is no arithmetic in this repository at all —
amounts arrive as display strings the harness produced with the system's own
formatter, because a decimal point placed here would be a financial figure
derived in an unaudited repository, which is the boundary ADR-0020 draws.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA_VERSION = "clofin.capture/2"
"""The one bundle schema this build reads.

`/2` added `identityBinding` to the stamp (clofin-core ADR-0022, amendment 1).
A manifest of any other version is refused before anything else is read, naming
the version it carries: one capture per site, of one schema. A `/1` capture is
not rendered with a blank where the binding goes — it is not rendered at all.
"""

IDENTITY_BINDINGS = ("instance-id", "port-exclusion")

INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,9})?)?Z")


class FixtureError(Exception):
    """A fixture is missing, unstamped, or not what the manifest says it is."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def resolve_pointer(document, pointer: str):
    """RFC 6901 JSON pointer, with a refusal instead of a None.

    A pointer that does not resolve means the page is about to display a
    figure no fixture contains, which is the one thing this site must not do.
    """
    if pointer in ("", "/"):
        return document
    if not pointer.startswith("/"):
        raise FixtureError(f"pointer must start with '/': {pointer!r}")
    node = document
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            try:
                node = node[int(token)]
            except (ValueError, IndexError) as exc:
                raise FixtureError(f"pointer {pointer!r} does not resolve at {token!r}") from exc
        elif isinstance(node, dict):
            if token not in node:
                raise FixtureError(f"pointer {pointer!r} does not resolve at {token!r}")
            node = node[token]
        else:
            raise FixtureError(f"pointer {pointer!r} runs past a leaf at {token!r}")
    return node


# --------------------------------------------------------------------------
# The stamp
# --------------------------------------------------------------------------

REQUIRED_PROVENANCE = [
    (["sourceCommit"], lambda v: isinstance(v, str) and len(v) == 40 and all(
        c in "0123456789abcdef" for c in v)),
    (["sourceCommitShort"], lambda v: isinstance(v, str) and len(v) == 7),
    (["sourceRef"], lambda v: isinstance(v, str) and v.strip() != ""),
    (["sourceUrl"], lambda v: isinstance(v, str) and v.startswith("https://github.com/")),
    (["tag"], lambda v: isinstance(v, str) and v.strip() != ""),
    (["tagKind"], lambda v: v in ("annotated", "lightweight")),
    (["releaseAudit", "label"], lambda v: isinstance(v, str) and v.strip() != ""),
    (["releaseAudit", "statement"], lambda v: isinstance(v, str) and v.startswith("RELEASE AUDIT:")),
    (["releaseAudit", "source"], lambda v: v in ("git-tag-annotation", "release-annotation-file")),
    (["releaseAudit", "sourceRef"], lambda v: isinstance(v, str) and v.strip() != ""),
    (["releaseAudit", "sourceSha256"], lambda v: isinstance(v, str)
     and re.fullmatch(r"[0-9a-f]{64}", v) is not None),
    # The harness's own instant format (`java.time.Instant`'s rendering), and
    # its own four-digit migration id — the predicates mirror the harness's
    # `required`, not only its field names.
    (["capturedAt"], lambda v: isinstance(v, str) and INSTANT.fullmatch(v) is not None),
    (["schemaVersionApplied"], lambda v: isinstance(v, str)
     and re.fullmatch(r"\d{4}", v) is not None),
    # How the capture established that the process it interrogated was the one
    # it started — exactly one of the two values the harness can stamp. What
    # each establishes is clofin-core ADR-0027 §3a's to say, not this file's.
    (["identityBinding"], lambda v: v in IDENTITY_BINDINGS),
    (["harness", "commit"], lambda v: isinstance(v, str) and v.strip() != ""),
]


def provenance_problems(document, name: str) -> list[str]:
    """Every reason `document` is not fully stamped, as sentences.

    The same field list the harness enforces before it writes — the same
    fields and, field by field, the same test of each — restated here rather
    than trusted: this repository is the one outside audit scope, so it
    checks the artifact in front of it instead of assuming the thing that
    produced it behaved.
    """
    problems = []
    if document.get("schemaVersion") != SCHEMA_VERSION:
        problems.append(
            f"{name}: schemaVersion is {document.get('schemaVersion')!r}, "
            f"expected {SCHEMA_VERSION!r}")
    prov = document.get("provenance")
    if not isinstance(prov, dict):
        return problems + [f"{name}: no provenance stamp at all"]
    for path, ok in REQUIRED_PROVENANCE:
        node = prov
        for key in path[:-1]:
            node = node.get(key, {}) if isinstance(node, dict) else {}
        value = node.get(path[-1]) if isinstance(node, dict) else None
        if not ok(value):
            problems.append(f"{name}: provenance.{'.'.join(path)} is missing or invalid "
                            f"({value!r})")
    return problems


# --------------------------------------------------------------------------
# The fixture set
# --------------------------------------------------------------------------

class Fixtures:
    """Everything one capture run produced, loaded and checked together."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.raw: dict[str, str] = {}
        self.docs: dict[str, dict] = {}

        self.manifest = self._load("manifest.json")
        version = self.manifest.get("schemaVersion") if isinstance(self.manifest, dict) else None
        if version != SCHEMA_VERSION:
            raise FixtureError(
                f"manifest.json is a {version!r} capture, and this build reads "
                f"{SCHEMA_VERSION!r} only — one capture per site, of one schema")
        self.service_info = self._load(self.manifest["fixture"]["path"])
        self.quotations = self._load(self.manifest["quotations"]["path"])
        self.bundles = [self._load(entry["path"]) for entry in self.manifest["bundles"]]
        self.bundle_paths = [entry["path"] for entry in self.manifest["bundles"]]

    def _load(self, relative: str) -> dict:
        path = self.root / relative
        if not path.is_file():
            raise FixtureError(f"the manifest names {relative}, which is not here")
        text = path.read_text(encoding="utf-8")
        self.raw[relative] = text
        document = json.loads(text)
        self.docs[relative] = document
        return document

    # -- integrity ---------------------------------------------------------

    def problems(self) -> list[str]:
        """Everything wrong with this fixture set, as sentences."""
        found: list[str] = []
        found += provenance_problems(self.manifest, "manifest.json")
        found += provenance_problems(self.service_info, self.manifest["fixture"]["path"])
        found += provenance_problems(self.quotations, self.manifest["quotations"]["path"])
        for path, bundle in zip(self.bundle_paths, self.bundles):
            found += provenance_problems(bundle, path)

        # The manifest's digests, against the files themselves. A manifest is
        # only an index if it is checked against what it indexes.
        for entry_name, entry in [("fixture", self.manifest["fixture"]),
                                  ("quotations", self.manifest["quotations"])]:
            actual = sha256_text(self.raw[entry["path"]])
            if actual != entry["sha256"]:
                found.append(f"{entry['path']}: sha256 is {actual[:12]}…, manifest "
                             f"{entry_name} says {entry['sha256'][:12]}…")
        for entry in self.manifest["bundles"]:
            actual = sha256_text(self.raw[entry["path"]])
            if actual != entry["sha256"]:
                found.append(f"{entry['path']}: sha256 is {actual[:12]}…, manifest says "
                             f"{entry['sha256'][:12]}…")

        # The scope statement, in all three places it is written down.
        disclaimer = self.disclaimer()
        body_sha = self.service_info["response"]["bodySha256"]
        for path, bundle in zip(self.bundle_paths, self.bundles):
            scope = bundle.get("scopeStatement", {})
            if scope.get("disclaimer") != disclaimer:
                found.append(f"{path}: its scope statement differs from the captured GET / body")
            if scope.get("bodySha256") != body_sha:
                found.append(f"{path}: its GET / digest differs from the captured fixture's")
        if sha256_text(self.service_info["response"]["bodyRaw"]) != body_sha:
            found.append("service-info.json: bodySha256 is not the digest of bodyRaw")
        found += self._self_report_problems()

        # Every capture in one set must be of one commit. A page showing two
        # scenarios from two source states with one provenance block would be
        # the most quietly wrong thing this site could do.
        # `.get` all the way down: this runs *after* the stamp check above, so
        # a fixture with no provenance at all has already been reported and
        # must not turn a report into a traceback.
        commits = {(d.get("provenance") or {}).get("sourceCommit")
                   for d in [self.manifest, self.service_info, self.quotations] + self.bundles}
        commits.discard(None)
        if len(commits) > 1:
            found.append(f"the fixture set spans more than one source commit: {sorted(commits)}")

        # Every sand-table cell must still equal the step it names.
        for path, bundle in zip(self.bundle_paths, self.bundles):
            found += self._sand_table_problems(path, bundle)
        return found

    def _self_report_problems(self) -> list[str]:
        """What the service said its commit was, against what the stamp says.

        The captured `GET /` carries `sourceCommit` from `ref-2` on: the
        service's own, self-reported answer. The stamp's `sourceCommit` was
        resolved by the harness from git. When the service reported one, the
        two must be the same string, byte for byte — a fixture whose service
        reported one commit while its stamp names another is a capture of
        something other than what it says (lesson L-19, on the consumer's
        side). Read from the raw body, because that is what the service sent.

        A `GET /` without the field is not a failure here: `ref-1` predates it,
        and the stamp says which binding such a capture used.
        """
        name = self.manifest["fixture"]["path"]
        try:
            body = json.loads(self.service_info["response"]["bodyRaw"])
        except (KeyError, TypeError, ValueError):
            return [f"{name}: the captured GET / body is not a JSON document"]
        if not isinstance(body, dict) or "sourceCommit" not in body:
            return []
        reported = body["sourceCommit"]
        found = []
        for where, document in [(name, self.service_info), ("manifest.json", self.manifest)]:
            stamped = (document.get("provenance") or {}).get("sourceCommit")
            if reported != stamped:
                found.append(
                    f"{name}: the captured GET / reports sourceCommit {reported!r}, and "
                    f"{where}'s stamp names {stamped!r} — the service said it was one "
                    f"commit and the capture is attributed to another")
        return found

    def _sand_table_problems(self, path: str, bundle: dict) -> list[str]:
        table = bundle.get("sandTable")
        if not table:
            return []
        steps = {step.get("id"): step for step in bundle.get("steps", [])}
        found = []
        for row in table.get("rows", []):
            for cell in row.get("cells", []):
                step = steps.get(cell.get("sourceStep"))
                if step is None:
                    found.append(f"{path}: sand-table row {row.get('label')!r} names step "
                                 f"{cell.get('sourceStep')!r}, which is not in the bundle")
                    continue
                captured = step.get("response", {}).get("body", {}).get("closingBalance")
                if captured != cell.get("closingBalance"):
                    found.append(f"{path}: sand-table cell for {cell.get('account')} in row "
                                 f"{row.get('label')!r} does not equal step "
                                 f"{cell.get('sourceStep')}'s closing balance")
                if step.get("account") != cell.get("account"):
                    found.append(f"{path}: sand-table cell for {cell.get('account')} reads a step "
                                 f"that captured {step.get('account')}")
        return found

    # -- accessors ---------------------------------------------------------

    def provenance(self) -> dict:
        return self.manifest["provenance"]

    def disclaimer(self) -> str:
        """The scope statement, from the captured `GET /` body itself.

        Read out of `response.bodyRaw` rather than out of the convenience
        field beside it: the raw body is what the service sent, and the whole
        value of `disclaimer-verbatim` is that the string on the page came
        from those bytes.
        """
        body = json.loads(self.service_info["response"]["bodyRaw"])
        text = body.get("disclaimer")
        if not isinstance(text, str) or not text.strip():
            raise FixtureError("the captured GET / body carries no disclaimer")
        return text

    def control(self, control_id: str) -> dict:
        for control in self.quotations["controls"]:
            if control["id"] == control_id:
                return control
        raise FixtureError(f"no control {control_id} in the captured quotations")

    def invariant(self, invariant_id: str) -> dict:
        for invariant in self.quotations["invariants"]:
            if invariant["id"] == invariant_id:
                return invariant
        raise FixtureError(f"no invariant {invariant_id} in the captured quotations")

    def bundle(self, bundle_id: str) -> tuple[str, dict]:
        for path, bundle in zip(self.bundle_paths, self.bundles):
            if bundle["scenario"]["id"] == bundle_id:
                return path, bundle
        raise FixtureError(f"no bundle {bundle_id} in the manifest")
