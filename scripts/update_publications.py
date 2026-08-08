#!/usr/bin/env python3
"""Add verified DOI links and BibTeX to incomplete publication entries.

Only high-confidence Crossref matches are applied. The script is intentionally
conservative: under-review work, patents, and ambiguous results are reported but
left unchanged.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PUBLICATIONS = ROOT / "_pages" / "publications.md"
DEFAULT_FILES = ROOT / "files"
SITE_FILES = "https://tamoghnaojha.github.io/files"
USER_AGENT = "tamoghnaojha-publication-maintainer/2.0 (mailto:t.ojha.1987@ieee.org)"
MIN_TITLE_SCORE = 0.96
PUBLICATION_PATTERN = re.compile(r"(?m)^\d+\.\s+.*?(?=\n\s*\n|\Z)", re.DOTALL)


@dataclass
class Result:
    title: str
    status: str
    detail: str = ""


def request(url: str, accept: str = "application/json") -> bytes:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def title_from(citation: str) -> str | None:
    # Supports plain quotes and common Unicode/smart-quote mojibake in old entries.
    match = re.search(r'(?:["“]|â€œ)(.*?)(?:["”]|â€)', citation)
    return match.group(1).strip() if match and len(match.group(1).strip()) >= 12 else None


def year_from(citation: str) -> int | None:
    years = re.findall(r"\b(?:19|20)\d{2}\b", citation)
    return int(years[-1]) if years else None


def crossref_match(title: str, year: int | None) -> tuple[dict | None, float]:
    query = urllib.parse.urlencode(
        {"query.bibliographic": f"{title} Tamoghna Ojha", "rows": 8,
         "select": "DOI,title,author,published,published-online,published-print,type"}
    )
    payload = json.loads(request("https://api.crossref.org/works?" + query))
    best: dict | None = None
    best_score = 0.0
    for item in payload.get("message", {}).get("items", []):
        candidate = (item.get("title") or [""])[0]
        score = SequenceMatcher(None, normalized(title), normalized(candidate)).ratio()
        authors = " ".join(author.get("family", "") for author in item.get("author", []))
        date = item.get("published-print") or item.get("published-online") or item.get("published") or {}
        parts = date.get("date-parts", [[None]])
        candidate_year = parts[0][0] if parts and parts[0] else None
        year_ok = not year or not candidate_year or abs(year - candidate_year) <= 1
        if re.search(r"\bojha\b", authors, re.IGNORECASE) and year_ok and score > best_score:
            best, best_score = item, score
    return (best, best_score) if best_score >= MIN_TITLE_SCORE else (None, best_score)


def bibtex_for(doi: str) -> str:
    encoded = urllib.parse.quote(doi, safe="")
    return request(
        "https://api.crossref.org/works/" + encoded + "/transform/application/x-bibtex",
        "application/x-bibtex",
    ).decode("utf-8").strip()


def bib_filename(doi: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "_", doi.lower()).strip("_")
    return "doi_" + safe + ".txt"


def is_ineligible(citation: str) -> bool:
    value = normalized(citation)
    return "under review" in value or "indian patent" in value


def update_block(block: str, files_dir: Path, dry_run: bool = False) -> tuple[str, Result | None]:
    citation = block.splitlines()[0]
    title = title_from(citation)
    if not title:
        return block, None
    has_link = "shields.io/badge/Link-" in block or "shields.io/badge/arXiv-" in block
    has_bibtex = "shields.io/badge/BibTeX-" in block
    if has_link and has_bibtex:
        return block, None
    if is_ineligible(citation):
        return block, Result(title, "skipped", "not yet eligible for publisher metadata")

    match, score = crossref_match(title, year_from(citation))
    if not match or not match.get("DOI"):
        return block, Result(title, "unmatched", f"best title score {score:.3f}")

    doi = match["DOI"]
    additions: list[str] = []
    updated_block = block
    existing_doi = re.search(r"https://doi\.org/([^\s)]+)", block, re.IGNORECASE)
    if existing_doi and existing_doi.group(1).lower() != doi.lower():
        updated_block = (
            block[:existing_doi.start(1)] + doi + block[existing_doi.end(1):]
        )
    if not has_link:
        additions.append(f"[![Link](https://img.shields.io/badge/Link-blue?style=flat-square)](https://doi.org/{doi})")
    if not has_bibtex:
        bibtex = bibtex_for(doi)
        if not bibtex.startswith("@"):
            return block, Result(title, "unmatched", "publisher returned invalid BibTeX")
        filename = bib_filename(doi)
        if not dry_run:
            files_dir.mkdir(parents=True, exist_ok=True)
            (files_dir / filename).write_text(bibtex + "\n", encoding="utf-8")
        additions.append(
            f"[![BibTeX](https://img.shields.io/badge/BibTeX-orange?style=flat-square)]({SITE_FILES}/{filename})"
        )
    if not additions and updated_block == block:
        return block, None

    lines = updated_block.rstrip().splitlines()
    if additions:
        if len(lines) > 1 and "shields.io/badge" in lines[-1]:
            lines[-1] += " " + " ".join(additions)
        else:
            lines.append(" ".join(additions))
    updated = "\n".join(lines) + "\n"
    return updated, Result(title, "updated" if not dry_run else "would update", f"DOI {doi}; score {score:.3f}")


def process(publications: Path, files_dir: Path, dry_run: bool = False) -> list[Result]:
    source = publications.read_text(encoding="utf-8")
    output: list[str] = []
    results: list[Result] = []
    cursor = 0
    for match in PUBLICATION_PATTERN.finditer(source):
        output.append(source[cursor:match.start()])
        try:
            block, result = update_block(match.group(0), files_dir, dry_run)
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as error:
            block = match.group(0)
            title = title_from(block.splitlines()[0]) or "Unknown publication"
            result = Result(title, "error", str(error))
        output.append(block)
        if result:
            results.append(result)
        cursor = match.end()
        time.sleep(0.15)
    output.append(source[cursor:])
    if not dry_run:
        publications.write_text("".join(output), encoding="utf-8")
    return results


def write_report(results: list[Result], path: Path | None) -> None:
    lines = ["# Publication maintenance report", ""]
    if not results:
        lines.append("All eligible publication entries already have links and BibTeX metadata.")
    else:
        lines.extend(["| Publication | Status | Detail |", "|---|---|---|"])
        for item in results:
            clean = lambda value: value.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {clean(item.title)} | {clean(item.status)} | {clean(item.detail)} |")
    report = "\n".join(lines) + "\n"
    print(report, end="")
    if path:
        path.write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report matches without changing files")
    parser.add_argument("--publications", type=Path, default=DEFAULT_PUBLICATIONS)
    parser.add_argument("--files-dir", type=Path, default=DEFAULT_FILES)
    parser.add_argument("--report", type=Path, help="write a Markdown run report")
    args = parser.parse_args()
    results = process(args.publications, args.files_dir, args.dry_run)
    write_report(results, args.report)


if __name__ == "__main__":
    main()
