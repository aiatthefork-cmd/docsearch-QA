# docsearch

A retrieval prototype for searching annual reports.

Point it at a folder of SEC filings, ask a question in plain English, and it
returns the passages it thinks are relevant. There is a set of test questions
with known answers, and a harness that scores how well the system finds the
evidence those answers depend on.

Built to see whether this approach is worth pursuing properly.

---

## Quick start

```bash
pip install -r requirements.txt

python search.py --ask "what were total operating revenues in 2023"
python evaluate.py --detail
```

The filings and the extracted text are both in the repo, so neither step below is
needed unless you want to rebuild or extend the corpus:

```bash
python fetch_filings.py --email you@example.com     # EDGAR  -> filings/
python extract.py                                   # filings/ -> corpus/filings.jsonl
```

Add `--tickers ODFL SNDR --years 2022 2023` to pull different companies.

---

## What's here

| | |
|---|---|
| `filings/` | The annual reports exactly as filed with the SEC. Open one in a browser. |
| `corpus/filings.jsonl` | The extracted text, one JSON record per filing, with metadata |
| `SOURCES.md` | Each filing, its extracted record, and a link to the original |
| `fetch_filings.py` | Downloads filings from EDGAR |
| `extract.py` | Converts a filing to text |
| `pipeline.py` | Chunking, embedding, search |
| `search.py` | Ask a question, inspect what got indexed |
| `questions.json` | Test questions, their correct answers, and the evidence that proves each |
| `evaluate.py` | Scores how well the system retrieves that evidence |
| `results/baseline.json` | The current scores |

---

## How it works

```
filing (.htm) ──▶ extract ──▶ text ──▶ 1000-char chunks ──▶ embeddings ──▶ index
                                                                              │
                                    question ──▶ embedding ──▶ nearest 5 chunks
```

Settings are at the top of `pipeline.py`: 1000-character chunks, 200 characters of
overlap, `all-MiniLM-L6-v2` embeddings, top 5 results. They are the usual starting
values and have not been tuned.

The system returns passages rather than written answers. That is deliberate for
now: an answer can only be as good as the evidence behind it, and it seemed worth
getting retrieval right before adding a layer that can paper over it.

---

## Measuring quality

`questions.json` holds test questions with their correct answers and, for each, the
exact text that has to be retrieved for that answer to be supportable.
`evaluate.py` checks whether it is:

```
  evidence recall@5       fraction of questions where the proving evidence was retrieved
  full evidence@5         fraction where every required span was retrieved
  MRR                     how high up it came - rank 1 beats rank 5
  provenance precision    share of retrieved chunks from the filing the question is about
  document coverage       for questions spanning filings, how many were represented
```

```bash
python evaluate.py --detail                          # where it fails, and what was missing
python evaluate.py -k 10                             # does more depth help?
python evaluate.py --compare results/baseline.json   # did a change help?
```

`--compare` reports the movement in each metric and names the questions that
started or stopped working, so a change can be judged rather than asserted.

---

## Inspecting it

Retrieval is the whole system here, so it's worth being able to see it:

```bash
python search.py --inspect wern-10k-fy2023    # how a filing got split, and where
python search.py --find "30,810"              # which chunks contain a phrase
python search.py --grep "30,810"              # which filings contain it
```

`--find` and `--grep` disagreeing is informative.

---

## Current state

It works. Whether it works *well enough* is a different question, and the numbers in
`results/baseline.json` are not flattering.

Known and unresolved:

- Chunking is fixed-width and ignores document structure entirely
- Filing metadata - company, fiscal year, section - is in `corpus/filings.jsonl` and
  in the headings, and nothing downstream uses it
- Tables survive extraction as pipe-delimited rows, but nothing special is done with them
- No re-ranking, no deduplication, no relevance threshold
- The whole index is rebuilt from scratch on every run

Some questions come back with passages that look right and aren't. Working out
which, and why, is the next job.

---

## Licence

Code under MIT. The filings are public domain, published by the United States
Securities and Exchange Commission.
