# 2026-11-02 candidate annotation pass (agent)

## What this is

An independent annotation pass over `evaluation/data/seed-v2-candidate/`, written from the
pinned documents in that directory. The machine draft
(`machine-draft-annotations.json`) was **not** opened before or during the pass.
Output: `evaluation/data/reviews/2026-11-02-agent-annotation-review.json`.

**This is agent review, not human review.** The file records `"status": "agent_reviewed"` and
a reviewer id of `agent:little-code-sauce@independent-pass-2026-11-02`. It must not be reported
as human review, and it does not close the "independent Q review" or the human-review gate.
`finalize_annotations.py` currently requires `status == "human_reviewed"`, so this file is
deliberately rejected by that gate as written.

## Method

- Every question was decided by reading the source documents only.
- Evidence offsets were never typed by hand. Each span is located by its exact quote, and the
  build fails if a quote is not unique inside its document. The importer's own
  `validate_candidate_questions` then re-derives `source[start:end] == quote` and the line
  numbers from the pinned bytes.
- Validator result: 60 reviewed annotations, 36 leakage groups, evidence spans 62.
- Category distribution: factual 15, rewrite 15, multi_evidence 10, chinese_keyword 10,
  no_answer 10 — every `no_answer` item is unanswerable, every other item is answerable.

## Judgment rules applied

1. **A positive list is not a negative fact.** Where a document enumerates what is supported,
   absence from that list is not treated as a statement that the other thing is unsupported.
   Such questions go to `answerable: false` with an empty evidence list.
2. **Superseded values are not current values.** `重试草案.md` says 20/60 seconds but is marked
   draft, unapproved and non-effective; `ADR-017.md` replaces it with 10/30. Current-value
   questions cite the ADR. Questions about the draft itself may cite the draft.
3. **Demo bounds are not product bounds.** The 6 MiB limit is explicitly labeled a synthetic
   demo limit, so questions about it must not be answered as a KnowFlow product constraint.
4. **Multi-evidence questions get every span needed to answer every clause**, from as many
   documents as the clauses require (for example retry values: draft + ADR).
5. **Unanswerable items still carry a short reference answer** describing what the corpus does
   and does not state, because the schema requires a non-empty `reference_answer` and the
   runner scores refusal separately from retrieval.

## Calls worth a second look

| Question | Call | Why |
|---|---|---|
| `candidate-59` (DOCX support) | unanswerable | The corpus lists TXT/Markdown/PDF and never mentions DOCX. Answering "no" would be inference from a positive list, which rule 1 forbids. This is the one `no_answer` item where a reader could argue either way. |
| `candidate-40` (failure retry cap) | answerable | The retry budget is stated as 0 automatic retries, which is the cap the question asks for; the second clause cites the cancel/delete rule from the same document. |
| `candidate-31` (Python publish) | answerable | Error code cites `超时取消.md`; the "cannot self-publish" clause cites `索引发布.md` because it states the ownership rule positively rather than as a cancel side effect. |
| `candidate-37` / `candidate-26` | answerable | Overlapping by design (same leakage group); kept as separate questions because one asks the checklist and the other the transaction boundary. |

## Not done here

- No human review, no blind holdout, no scoring run.
- No comparison against the machine draft has been made yet; if one is run later, disagreement
  counts belong in this record rather than being resolved by editing annotations to match.
