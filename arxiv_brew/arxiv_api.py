"""arXiv API and scraping utilities."""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

from . import USER_AGENT

_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"
_API_BASE = "https://export.arxiv.org/api/query"


@dataclass
class Paper:
    id: str
    title: str
    authors: list[str]
    abstract: str
    published: str
    updated: str
    categories: list[str]
    primary_category: str
    version: int = 1
    abs_url: str = ""
    html_url: str = ""
    pdf_url: str = ""
    matched_clusters: list[str] = field(default_factory=list)
    relevance_score: float = 0.0
    affiliations: list[str] = field(default_factory=list)
    corresponding_author: Optional[str] = None
    content_path: Optional[str] = None
    download_status: str = ""

    def __post_init__(self):
        if not self.abs_url:
            self.abs_url = f"https://arxiv.org/abs/{self.id}"
        if not self.html_url:
            self.html_url = f"https://arxiv.org/html/{self.id}v{self.version}"
        if not self.pdf_url:
            self.pdf_url = f"https://arxiv.org/pdf/{self.id}.pdf"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "authors": self.authors,
            "abstract": self.abstract, "published": self.published,
            "updated": self.updated, "categories": self.categories,
            "primary_category": self.primary_category, "version": self.version,
            "abs_url": self.abs_url, "html_url": self.html_url,
            "pdf_url": self.pdf_url, "matched_clusters": self.matched_clusters,
            "relevance_score": self.relevance_score,
            "affiliations": self.affiliations,
            "corresponding_author": self.corresponding_author,
            "content_path": self.content_path,
            "download_status": self.download_status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Paper:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _request(url: str, timeout: int = 30) -> bytes:
    # Ensure HTTPS to avoid redirect-induced timeouts
    if url.startswith("http://"):
        url = "https://" + url[7:]
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt < 2:
                time.sleep(3)
                continue
            raise
    raise RuntimeError(f"Failed to fetch {url} after 3 attempts")


def fetch_new_ids(category: str) -> list[str]:
    """Scrape arxiv.org/list/{category}/new for today's new + cross-listed IDs."""
    url = f"https://arxiv.org/list/{category}/new"
    try:
        html = _request(url).decode("utf-8", errors="replace")
    except Exception:
        return []

    cutoff = html.find("Replacement submissions")
    if cutoff > 0:
        html = html[:cutoff]

    id_pattern = re.compile(r"(?:arXiv:|/abs/)(\d{4}\.\d{4,5})")
    return list(dict.fromkeys(id_pattern.findall(html)))


def fetch_new_ids_multi(categories: list[str]) -> list[str]:
    all_ids: list[str] = []
    for cat in categories:
        all_ids.extend(fetch_new_ids(cat))
    return list(dict.fromkeys(all_ids))


def _parse_entry(entry: ET.Element) -> Paper:
    raw_id = entry.findtext(f"{{{_ATOM_NS}}}id", "")
    # Extract version from raw id (e.g. "2006.14672v2" → id="2006.14672", version=2)
    version = 1
    if "/abs/" in raw_id:
        id_with_ver = raw_id.split("/abs/")[-1]
        m = re.match(r"(.+?)v(\d+)$", id_with_ver)
        if m:
            arxiv_id = m.group(1)
            version = int(m.group(2))
        else:
            arxiv_id = id_with_ver
    else:
        arxiv_id = raw_id

    title = re.sub(r"\s+", " ", (entry.findtext(f"{{{_ATOM_NS}}}title", "") or "").strip())
    abstract = re.sub(r"\s+", " ", (entry.findtext(f"{{{_ATOM_NS}}}summary", "") or "").strip())
    published = (entry.findtext(f"{{{_ATOM_NS}}}published", "") or "")[:10]
    updated = (entry.findtext(f"{{{_ATOM_NS}}}updated", "") or "")[:10]

    authors = [
        a.findtext(f"{{{_ATOM_NS}}}name", "")
        for a in entry.findall(f"{{{_ATOM_NS}}}author")
    ]
    categories = [
        c.get("term", "") for c in entry.findall(f"{{{_ATOM_NS}}}category")
        if c.get("term")
    ]

    primary_el = entry.find(f"{{{_ARXIV_NS}}}primary_category")
    primary_cat = primary_el.get("term", "") if primary_el is not None else ""
    if not primary_cat and categories:
        primary_cat = categories[0]

    return Paper(
        id=arxiv_id, title=title, authors=authors, abstract=abstract,
        published=published, updated=updated,
        categories=categories, primary_category=primary_cat,
        version=version,
    )


def fetch_metadata(arxiv_ids: list[str], chunk_size: int = 50) -> list[Paper]:
    papers: list[Paper] = []
    for i in range(0, len(arxiv_ids), chunk_size):
        chunk = arxiv_ids[i:i + chunk_size]
        id_list = ",".join(chunk)
        url = f"{_API_BASE}?id_list={id_list}&max_results={len(chunk)}"
        try:
            data = _request(url)
            root = ET.fromstring(data)
        except Exception:
            continue
        for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
            paper = _parse_entry(entry)
            if paper.title:
                papers.append(paper)
        if i + chunk_size < len(arxiv_ids):
            time.sleep(3)
    return papers


def download_html(paper: Paper) -> str | None:
    """Download and extract text from arXiv HTML version."""
    try:
        html = _request(paper.html_url, timeout=60).decode("utf-8", errors="replace")
    except Exception:
        return None

    html = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    for tag, prefix in [("h1", "# "), ("h2", "## "), ("h3", "### "), ("h4", "#### ")]:
        html = re.sub(rf"<{tag}[^>]*>(.*?)</{tag}>", rf"\n{prefix}\1\n", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"<p[^>]*>", "\n", html, flags=re.I)
    html = re.sub(r"</p>", "\n", html, flags=re.I)
    html = re.sub(r"<li[^>]*>", "\n- ", html, flags=re.I)
    html = re.sub(r"<(b|strong)[^>]*>(.*?)</\1>", r"**\2**", html, flags=re.S | re.I)
    html = re.sub(r"<(i|em)[^>]*>(.*?)</\1>", r"*\2*", html, flags=re.S | re.I)
    html = re.sub(r'<math[^>]*alttext="([^"]*)"[^>]*>.*?</math>', r"$\1$", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()
    return text if len(text) > 500 else None


def download_pdf_text(paper: Paper, save_path: str | None = None) -> str | None:
    try:
        data = _request(paper.pdf_url, timeout=60)
    except Exception:
        return None
    if len(data) < 10240:
        return None

    from pathlib import Path as P
    if save_path:
        P(save_path).parent.mkdir(parents=True, exist_ok=True)
        P(save_path).write_bytes(data)

    import subprocess, tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", tmp, "-"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and len(result.stdout) > 500:
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    finally:
        P(tmp).unlink(missing_ok=True)

    try:
        import fitz
        doc = fitz.open(stream=data, filetype="pdf")
        text = "\n\n".join(page.get_text() for page in doc)
        doc.close()
        if len(text) > 500:
            return text
    except ImportError:
        pass

    return None
