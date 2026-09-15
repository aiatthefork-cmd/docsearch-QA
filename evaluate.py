#!/usr/bin/env python3
"""Measure how well this system retrieves the evidence its answers depend on.

    python evaluate.py                 # score at k=5, write results/baseline.json
    python evaluate.py -k 10           # score at a different depth
    python evaluate.py --detail        # per-question breakdown
    python evaluate.py --compare results/baseline.json

An answer can only be as good as the evidence behind it. If the passage that
proves a fact never reaches the model, no amount of prompting recovers it - so
what is measured here is whether the evidence arrives, and how cleanly.

Metrics
-------
evidence recall@k   fraction of questions where at least one retrieved chunk
                    contains the evidence that proves the answer
full evidence@k     fraction where EVERY required evidence span is present -
                    stricter, and the one that matters for multi-fact answers
answerable@k        full evidence present AND no distractor alongside it. A
                    distractor is a value that makes the answer ambiguous rather
                    than supported: the 2022 revenue figure sitting next to the
                    2021 one, with nothing in the context saying which is which.
                    Recall alone calls that a success. It isn't.
MRR                 mean reciprocal rank of the first chunk carrying evidence,
                    so retrieving it at position 1 scores better than at 5
provenance          fraction of retrieved chunks that come from a filing the
                    question is actually about - the rest are distractors
doc coverage        for questions spanning several filings, the fraction of
                    required filings represented at all
"""

import argparse
import json
import os
import sys

from pipeline import Index, TOP_K


def score_question(q, hits):
    """Score one question against its retrieved chunks."""
    blob = "\n".join(h["text"] for h in hits).lower()
    spans = q.get("evidence") or []

    present = [s for s in spans if s.lower() in blob]
    recall = bool(present) if spans else None
    full = (len(present) == len(spans)) if spans else None

    distractors = q.get("distractors") or []
    found_distractors = [d for d in distractors if d.lower() in blob]
    answerable = (full and not found_distractors) if spans else None

    rank = 0
    for i, h in enumerate(hits, 1):
        if any(s.lower() in h["text"].lower() for s in spans):
            rank = i
            break
    rr = 1.0 / rank if rank else 0.0

    expect = q["expect_docs"]
    if expect == "corpus":
        wanted = {h["doc_id"] for h in hits}          # every filing is fair game
        provenance = 1.0
        coverage = None
    else:
        wanted = set(expect)
        on_target = [h for h in hits if h["doc_id"] in wanted]
        provenance = len(on_target) / len(hits) if hits else 0.0
        coverage = len({h["doc_id"] for h in on_target}) / len(wanted)

    return {"id": q["id"], "question": q["question"],
            "evidence_found": recall, "all_evidence_found": full,
            "answerable": answerable, "distractors_present": found_distractors,
            "evidence_rank": rank, "reciprocal_rank": rr,
            "provenance": round(provenance, 3),
            "doc_coverage": None if coverage is None else round(coverage, 3),
            "missing_evidence": [s for s in spans if s not in present],
            "retrieved": [f"{h['doc_id']}#{h['chunk']}" for h in hits]}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-k", type=int, default=TOP_K, help="retrieval depth")
    ap.add_argument("--questions", default="questions.json")
    ap.add_argument("--detail", action="store_true", help="per-question breakdown")
    ap.add_argument("--compare", metavar="FILE", help="compare against an earlier run")
    ap.add_argument("--out", default="results/baseline.json")
    args = ap.parse_args()

    questions = json.load(open(args.questions, encoding="utf-8"))["questions"]
    scored_qs = [q for q in questions if q.get("evidence")]

    index = Index().build(verbose=False)
    print(f"{len({m['doc_id'] for m in index.meta})} filings, "
          f"{len(index.chunks)} chunks, k={args.k}\n")

    results = [score_question(q, index.search(q["question"], k=args.k)) for q in scored_qs]

    recall = mean([r["evidence_found"] for r in results])
    full = mean([r["all_evidence_found"] for r in results])
    answerable = mean([r["answerable"] for r in results])
    mrr = mean([r["reciprocal_rank"] for r in results])
    prov = mean([r["provenance"] for r in results])
    cov = mean([r["doc_coverage"] for r in results])

    print("=" * 62)
    print(f"  evidence recall@{args.k}      {recall:>6.1%}   "
          f"({sum(1 for r in results if r['evidence_found'])}/{len(results)} questions)")
    print(f"  full evidence@{args.k}        {full:>6.1%}")
    print(f"  answerable@{args.k}           {answerable:>6.1%}   "
          f"(evidence present, no competing value alongside it)")
    print(f"  MRR                     {mrr:>6.3f}")
    print(f"  provenance precision    {prov:>6.1%}   (retrieved chunks from the right filing)")
    print(f"  document coverage       {cov:>6.1%}")
    print("=" * 62)

    if args.detail:
        print(f"\n{'id':<5} {'found':<6} {'all':<5} {'ans':<5} {'rank':<5} {'prov':<6} question")
        print("-" * 84)
        for r in results:
            print(f"{r['id']:<5} {'yes' if r['evidence_found'] else 'NO':<6} "
                  f"{'yes' if r['all_evidence_found'] else 'no':<5} "
                  f"{'yes' if r['answerable'] else 'NO':<5} "
                  f"{r['evidence_rank'] or '-':<5} {r['provenance']:<6.2f} "
                  f"{r['question'][:40]}")
        ambiguous = [r for r in results if r["all_evidence_found"] and not r["answerable"]]
        if ambiguous:
            print(f"\nevidence retrieved but not answerable ({len(ambiguous)}) - a "
                  f"competing value came with it:")
            for r in ambiguous:
                print(f"  {r['id']}  alongside: {r['distractors_present']}")
        missing = [r for r in results if not r["evidence_found"]]
        if missing:
            print(f"\nevidence never retrieved ({len(missing)}):")
            for r in missing:
                print(f"  {r['id']}  missing {r['missing_evidence']}")
                print(f"        got {r['retrieved']}")

    summary = {"k": args.k, "questions": len(results),
               "evidence_recall": round(recall, 4), "full_evidence": round(full, 4),
               "answerable": round(answerable, 4),
               "mrr": round(mrr, 4), "provenance": round(prov, 4),
               "doc_coverage": round(cov, 4),
               "chunk_size": __import__("pipeline").CHUNK_SIZE,
               "chunk_overlap": __import__("pipeline").CHUNK_OVERLAP,
               "model": __import__("pipeline").EMBEDDING_MODEL,
               "per_question": results}

    if args.compare:
        old = json.load(open(args.compare, encoding="utf-8"))
        print(f"\nagainst {args.compare} (k={old['k']}, {old['model'].split('/')[-1]}, "
              f"chunk {old['chunk_size']}/{old['chunk_overlap']}):")
        for name, key in (("evidence recall", "evidence_recall"), ("full evidence", "full_evidence"),
                          ("answerable", "answerable"),
                          ("MRR", "mrr"), ("provenance", "provenance"), ("coverage", "doc_coverage")):
            d = summary[key] - old[key]
            arrow = "+" if d > 0 else ""
            print(f"  {name:<18} {old[key]:>7.3f} -> {summary[key]:>7.3f}   {arrow}{d:.3f}")
        was = {r["id"] for r in old["per_question"] if r["evidence_found"]}
        now = {r["id"] for r in results if r["evidence_found"]}
        if now - was:
            print(f"  newly found:  {sorted(now - was)}")
        if was - now:
            print(f"  newly lost:   {sorted(was - now)}")
    else:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(summary, open(args.out, "w", encoding="utf-8"), indent=1)
        print(f"\nwritten to {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
