#!/usr/bin/env python3
"""Add high-confidence Crossref links and BibTeX to incomplete publications."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLICATIONS = ROOT / "_pages" / "publications.md"
FILES = ROOT / "files"
SITE_FILES = "https://tamoghnaojha.github.io/files"
USER_AGENT = "tamoghnaojha-publication-updater/1.0 (https://tamoghnaojha.github.io/)"
MIN_TITLE_SCORE = 0.94


def request(url: str, accept: str = "application/json") -> bytes:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def title_from(citation: str) -> str | None:
    match = re.search(r'[“"]([^”"]{12,})[”"]', citation)
    return match.group(1).strip() if match else None


def year_from(citation: str) -> int | None:
    years = re.findall(r"\b(?:19|20)\d{2}\b", citation)
    return int(years[-1]) if years else None


def crossref_match(title: str, year: int | None) -> dict | None:
    query = urllib.parse.urlencode({"query.title": title, "rows": 5, "select": "DOI,title,author,published"})
    payload = json.loads(request("https://api.crossref.org/works?" + query))
    best = None
    best_score = 0.0
    for item in payload["message"]["items"]:
        candidate = (item.get("title") or [""])[0]
        score = SequenceMatcher(None, normalized(title), normalized(candidate)).ratio()
        authors = " ".join(author.get("family", "") for author in item.get("author", []))
        dates = item.get("published", {}).get("date-parts", [[None]])
        candidate_year = dates[0][0] if dates and dates[0] else None
        year_ok = not year or not candidate_year or abs(year - candidate_year) <= 1
        if "ojha" in authors.lower() and year_ok and score > best_score:
            best, best_score = item, score
    return best if best_score >= MIN_TITLE_SCORE else None


def bibtex_for(doi: str) -> str:
    encoded = urllib.parse.quote(doi, safe="")
    return request(
        "https://api.crossref.org/works/" + encoded + "/transform/application/x-bibtex",
        "application/x-bibtex",
    ).decode("utf-8").strip()


def bib_filename(doi: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "_", doi.lower()).strip("_")
    return "doi_" + safe + ".txt"


def update_block(block: str) -> str:
    citation = block.splitlines()[0]
    title = title_from(citation)
    if not title:
        return block
    has_paper = "shields.io/badge/Link-" in block or "shields.io/badge/arXiv-" in block
    has_bibtex = "shields.io/badge/BibTeX-" in block
    if has_paper and has_bibtex:
        return block

    match = crossref_match(title, year_from(citation))
    if not match or not match.get("DOI"):
        return block
    doi = match["DOI"]
    additions = []
    if not has_paper:
        additions.append(f"[![Link](https://img.shields.io/badge/Link-blue?style=flat-square)](https://doi.org/{doi})")
    if not has_bibtex:
        try:
            bibtex = bibtex_for(doi)
        except (urllib.error.URLError, TimeoutError):
            bibtex = ""
        if bibtex.startswith("@"):
            filename = bib_filename(doi)
            (FILES / filename).write_text(bibtex + "\n", encoding="utf-8")
            additions.append(f"[![BibTeX](https://img.shields.io/badge/BibTeX-orange?style=flat-square)]({SITE_FILES}/{filename})")
    if not additions:
        return block
    lines = block.rstrip().splitlines()
    if len(lines) > 1 and "shields.io/badge" in lines[-1]:
        lines[-1] += " " + " ".join(additions)
    else:
        lines.append(" ".join(additions))
    return "\n".join(lines) + "\n"


def main() -> None:
    text = PUBLICATIONS.read_text(encoding="utf-8")
    pattern = re.compile(r"(?m)^\d+\.\s+.*?(?=\n\s*\n|\Z)", re.DOTALL)
    blocks = []
    cursor = 0
    for match in pattern.finditer(text):
        blocks.append(text[cursor : match.start()])
        try:
            blocks.append(update_block(match.group(0)))
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as error:
            print(f"Skipped lookup: {error}")
            blocks.append(match.group(0))
        cursor = match.end()
        time.sleep(0.15)
    blocks.append(text[cursor:])
    PUBLICATIONS.write_text("".join(blocks), encoding="utf-8")


if __name__ == "__main__":
    main()
