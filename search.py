#!/usr/bin/env python3
"""Ask the corpus a question and see what comes back.

    python search.py --ask "what were total revenues in 2023"
    python search.py --ask "driver shortage" -k 10
    python search.py --inspect wern-10k-fy2023      # how a filing was chunked
    python search.py --find "30,810"                # which chunks hold a phrase
    python search.py --grep "30,810"                # which filings hold it
    python search.py --questions                    # run the question set
    python search.py --questions questions_holdout.json
"""

import argparse
import json
import os
import sys

from pipeline import Index, TOP_K


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ask")
    ap.add_argument("--inspect", metavar="DOC_ID")
    ap.add_argument("--find", metavar="PHRASE")
    ap.add_argument("--grep", metavar="PHRASE")
    ap.add_argument("--questions", nargs="?", const="questions.json",
                    metavar="FILE", help="run a question set (default questions.json)")
    ap.add_argument("-k", type=int, default=TOP_K)
    args = ap.parse_args()

    if not any([args.ask, args.inspect, args.find, args.grep, args.questions]):
        ap.print_help()
        return 0

    index = Index().build(verbose=bool(args.ask or args.questions))

    if args.inspect:
        index.show_chunks(args.inspect); return 0
    if args.find:
        index.find(args.find); return 0
    if args.grep:
        index.grep(args.grep); return 0

    def show(question):
        print(f"\nQ: {question}\n")
        for rank, h in enumerate(index.search(question, k=args.k), 1):
            print(f"  [{rank}] {h['score']:.3f}  {h['doc_id']}  chunk {h['chunk']}")
            print(f"      {' '.join(h['text'].split())[:260]}...\n")

    if args.ask:
        show(args.ask)
    else:
        for q in json.load(open(args.questions, encoding="utf-8"))["questions"]:
            print("=" * 74)
            if q.get("answer"):
                print(f"{q['id']}  correct answer: {q['answer']}")
            else:
                print(f"{q['id']}")
            show(q["question"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
