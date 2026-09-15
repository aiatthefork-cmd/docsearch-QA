"""The search pipeline.

Read the extracted filings, split them into chunks, embed the chunks, and at
query time embed the question and return the nearest ones.

Settings are the common defaults and have not been tuned.
"""

import json
import os

import numpy as np
from sentence_transformers import SentenceTransformer

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
TOP_K = 5
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

CORPUS = "corpus/filings.jsonl"


def load_filings(path=CORPUS):
    if not os.path.exists(path):
        raise SystemExit(f"{path} not found - run fetch_filings.py then extract.py")
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def split(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Fixed-width character windows with a fixed overlap."""
    out, start = [], 0
    while start < len(text):
        out.append(text[start:start + size])
        start += size - overlap
    return [c for c in out if c.strip()]


class Index:
    """Chunks, their embeddings, and where each chunk came from."""

    def __init__(self, path=CORPUS, model_name=EMBEDDING_MODEL):
        self.path = path
        self.model = SentenceTransformer(model_name)
        self.chunks = []
        self.meta = []          # one dict per chunk: doc_id, ticker, fiscal_year, offset
        self.vectors = None

    def build(self, verbose=True):
        for f in load_filings(self.path):
            for i, piece in enumerate(split(f["text"])):
                self.chunks.append(piece)
                self.meta.append({"doc_id": f["doc_id"], "ticker": f["ticker"],
                                  "fiscal_year": f["fiscal_year"], "chunk": i})
        self.vectors = self.model.encode(self.chunks, normalize_embeddings=True,
                                         show_progress_bar=verbose, batch_size=64)
        if verbose:
            print(f"indexed {len({m['doc_id'] for m in self.meta})} filings "
                  f"into {len(self.chunks)} chunks")
        return self

    def search(self, question, k=TOP_K):
        q = self.model.encode([question], normalize_embeddings=True)[0]
        scores = self.vectors @ q
        order = np.argsort(scores)[::-1][:k]
        return [{"text": self.chunks[i], "score": float(scores[i]), **self.meta[i]}
                for i in order]

    # ------------------------------------------------------------ inspection

    def show_chunks(self, doc_id, preview=140):
        """How one filing was split, and where the boundaries fell."""
        f = next(x for x in load_filings(self.path) if x["doc_id"] == doc_id)
        pieces = split(f["text"])
        print(f"{doc_id} -> {len(pieces)} chunks\n")
        for i, c in enumerate(pieces):
            flat = " ".join(c.split())
            print(f"  [{i}] {len(c):>5} chars")
            print(f"      starts: {flat[:preview]}...")
            print(f"      ends:   ...{flat[-70:]}\n")

    def find(self, phrase):
        """Which indexed chunks contain this phrase."""
        hits = [(m["doc_id"], m["chunk"]) for c, m in zip(self.chunks, self.meta)
                if phrase.lower() in c.lower()]
        if not hits:
            print(f"{phrase!r} appears in NO indexed chunk")
        for doc, i in hits:
            print(f"  {doc}  chunk {i}")
        return hits

    def grep(self, phrase):
        """Which filings contain this phrase, whatever the index thinks."""
        out = [f["doc_id"] for f in load_filings(self.path)
               if phrase.lower() in f["text"].lower()]
        print(out or f"{phrase!r} not found in any filing")
        return out
