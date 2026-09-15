#!/usr/bin/env python3
"""Turn the filings in ./filings into the text the search pipeline uses.

    python extract.py

Writes corpus/filings.jsonl - one JSON record per filing:

    {"doc_id", "ticker", "company", "fiscal_year", "form", "source_url", "text"}

Tables are kept as pipe-delimited rows rather than flattened, because a financial
filing without its tables is not a financial filing.
"""

import json
import os
import re
import sys


def html_to_text(html):
    from bs4 import BeautifulSoup, NavigableString

    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style"]):
        tag.decompose()

    # The inline-XBRL header holds thousands of machine identifiers that a
    # browser never renders. Drop it whole; keep the wrappers around visible
    # facts, which do carry real numbers.
    for tag in soup.find_all(re.compile(r"^ix:(header|hidden|references|resources)$", re.I)):
        tag.decompose()
    for tag in soup.find_all(re.compile(r"^(xbrli|link|xlink):", re.I)):
        tag.decompose()
    for tag in soup.find_all(re.compile(r"^ix:", re.I)):
        tag.unwrap()

    for br in soup.find_all("br"):
        br.replace_with("\n")

    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [" ".join(td.get_text(" ", strip=True).split())
                     for td in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c not in ("", "$", ")", "(")]
            if any(cells):
                rows.append("| " + " | ".join(cells) + " |")
        table.replace_with("\n\n" + "\n".join(rows) + "\n\n" if rows else "")

    BLOCKS = ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "section")
    for tag in soup.find_all(BLOCKS):
        tag.append(NavigableString("\n\n"))

    text = soup.get_text("")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _trim_preamble(text.strip())


# Filers format the XBRL preamble differently, so as a backstop drop anything
# before the cover page. Only applied when a cover marker is found near the
# start, so a document without one is left alone.
_COVER = re.compile(
    r"(UNITED STATES\s*\n?\s*SECURITIES AND EXCHANGE COMMISSION"
    r"|ANNUAL REPORT PURSUANT TO SECTION"
    r"|FORM\s+10-K)", re.I)


def _trim_preamble(text, window=60000):
    m = _COVER.search(text[:window])
    return text[m.start():] if m and m.start() > 500 else text


def main():
    try:
        import bs4, lxml  # noqa: F401
    except ImportError:
        sys.exit("needs beautifulsoup4 and lxml:  pip install -r requirements.txt")

    if not os.path.exists("filings/index.json"):
        sys.exit("filings/index.json not found - run fetch_filings.py first")

    index = json.load(open("filings/index.json", encoding="utf-8"))["filings"]
    os.makedirs("corpus", exist_ok=True)
    out_path = "corpus/filings.jsonl"

    total_in = total_out = 0
    with open(out_path, "w", encoding="utf-8", newline="\n") as out:
        for f in index:
            src = os.path.join("filings", f["file"])
            html = open(src, encoding="utf-8").read()
            text = html_to_text(html)
            total_in += len(html)
            total_out += len(text)
            record = {k: f[k] for k in
                      ("doc_id", "ticker", "company", "fiscal_year", "form", "source_url")}
            record["text"] = text
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"  {f['doc_id']:<20} {len(html):>10,} -> {len(text):>9,} chars")

    _write_sources(index)

    print(f"\n{len(index)} filings, {total_in:,} -> {total_out:,} chars "
          f"({total_out/total_in:.1%} kept) in {out_path}")
    print("next: python search.py --ask \"what were total revenues in 2023\"")


def _write_sources(index):
    """A human-readable index of where each filing came from."""
    lines = ["# Source filings", "",
             "Every document here is a 10-K annual report filed with the United States",
             "Securities and Exchange Commission. The filings are public domain.",
             "",
             "`filings/` holds them exactly as filed - open one in a browser and it renders",
             "the way the SEC published it, tables laid out and headings in place.",
             "`corpus/filings.jsonl` holds the extracted text, which is what the search",
             "pipeline actually sees. They are not the same thing.",
             "",
             "| Company | FY | As filed | Extracted | Original |",
             "|---|---|---|---|---|"]
    for f in index:
        lines.append(f"| {f['company'].title()} | {f['fiscal_year']} | "
                     f"`filings/{f['file']}` | `{f['doc_id']}` | "
                     f"[EDGAR]({f['source_url']}) |")
    lines.append("")
    with open("SOURCES.md", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    main()
