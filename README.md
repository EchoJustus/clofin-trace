# clofin-trace

A replay walkthrough of [CloFin](https://github.com/EchoJustus/clofin-core) —
an open-source, synthetic-data reference implementation of an enterprise
payments and reconciliation core.

**This repository contains no CloFin system code and enforces no controls.**
It presents captured output; it computes nothing.

## What this site shows

Every figure on this site is **replayed captured output** of
[`clofin-core` at tag `ref-1`, commit `5c7b4ba`](https://github.com/EchoJustus/clofin-core/tree/5c7b4badced5e807e1022fce44cbcad38c6d2095).
If a value cannot be traced to captured output of that commit, it does not
appear ([ADR-0020](https://github.com/EchoJustus/clofin-core/blob/main/docs/ADR/0020-two-repositories-and-the-generate-replay-rules.md),
RULE 2 — replay, never fake).

`ref-1`'s release audit was **partial — charter items 1–4 of 8**, with items
5–7 carried forward to `ref-2`. This walkthrough states the coverage its
source actually has, read from the tag's own annotation, and never describes
it as "audited" without that qualifier.

## Scope

Quoted verbatim from the system's own `GET /` response:

> CloFin operates on synthetic data only. It is not connected to any bank,
> payment scheme or central bank, holds no regulatory authorisation, and
> never processes real funds.

## Licence

Eclipse Public License 2.0 — see [LICENSE](LICENSE), matching `clofin-core`.
