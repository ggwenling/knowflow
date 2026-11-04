# Blind rounds summary (v1 / v2 / v3) — 2026-11-05

Short closeout after citation-fix work. **No new collects; no blind v4.** Soft spend target `< CNY 2` was exceeded; real provider calls are paused.

## Judged gate table

| Metric | Blind v1 (original judged) | Blind v2 (citation fix) | Blind v3 (prune fix) |
| --- | ---: | ---: | ---: |
| Recall@5 | 1.000 | 1.000 | 0.9744 |
| MRR@10 | 1.000 | 0.9667 | 1.000 |
| Support | 0.875 (fail) | 1.000 | 0.9167 |
| Citation | 0.880 (fail) | 1.000 | 0.9655 |
| Unanswerable refusal | 0.800 (fail) | 1.000 | 1.000 |
| Answerable answer | 1.000 | **0.7333 (fail)** | **0.800 (fail)** |
| Gate | **failed** | **failed** | **failed** |
| Collect HEAD | (pre-citation-fix) | `aea779a` | `f00a17d` |

v1 figures: `docs/evaluation/assets-box-blind-20261105-original-judged-summary.json`.  
v2/v3: `assets-box-blind-20261105-v2-judged-summary.json`, `…-v3-judged-summary.json`.

## What each fix did

1. **Citation fix** (`90e053c` → `aea779a`): per-claim citation prompt + post-generation grounding verifier; stream buffers until validation. Blind v2 citation/support/unanswerable hit 1.0, but hard-refuse-on-any-ungrounded-claim caused **4/15 false refusals** (answerable 0.733).
2. **Prune fix** (`d077e6a` → `f00a17d`): drop/re-attach ungrounded claims; refuse only when nothing grounded remains; URL-boundary Sol P1/P1b/P1c. Public seed-v2 dev+holdout gates passed (answerable 1.0). Blind v3 answerable rose to **0.800** (still `< 0.90`); one answered item failed support+citation.

## Residual issue

Blind v3 still fails the quality gate on **answerable_answer_rate = 0.800** (12/15). False refusals remain the dominant residual after prune. Secondary: one answered item with support/citation failure (`bddfd2ca1a50`).

## Recommended next fix (design only — do not implement under current pause)

- **Calibrate prune/refuse boundary for under-citation**, not only over-citation: when retrieval is strong (high Recall/MRR) but the model emits a short/partial answer that the verifier strips to empty, prefer a **single bounded re-ask** (or claim-level repair) with the same evidence before canonical refusal.
- Keep hard refusal for true empty evidence and for unanswerable gold.
- Gate any such change only on **public seed-v2 dev → holdout** with dual LLM judges; do **not** tune on blind packs.
- Optional observability: per-question prune reason codes (ungrounded / citation-set mismatch / empty-after-prune) in prediction sidecars for offline analysis without re-collecting.

## Spend

Shared citation-fix ledger  
`/workspace/knowflow-runtime/data/budget/citation-fix-20261105-023600.sqlite3`:

| Checkpoint | Paid reservations | Reserved CNY |
| --- | ---: | ---: |
| Blind v3 collect-end snapshot | 516 | **1.268328** |
| Ledger at closeout (frozen) | 1092 | **2.684136** |

Post-collection growth (+576 DeepSeek peak reservations after the v3 status snapshot): live Java+AI were left running with `KNOWFLOW_BUDGET_LEDGER_PATH` pointed at this ledger (`provider_budget` reserves on every DeepSeek attempt). No further `run-real-collect` log after v3; growth is attributed to that leftover real-AI process boundary (not LLM judges). **Services stopped; CodeBuddy leftover session killed; ledger mtime stable; no new real collects.**

Project soft target `< CNY 2` exceeded. Supervisor pause on real model/API calls remains in force.

## CI note (this closeout)

Web engineering E2E failed from first citation-fix commit `90e053c` onward: `e2e/knowledge-desk.spec.ts` required a `delta` on error/cancelled/timeout streams, but answer text is intentionally buffered until citation validation (`services/ai/docs/answer-streaming.md`). Fix: require `delta` only for `completed` terminals.
