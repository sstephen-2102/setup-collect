#!/usr/bin/env python3
"""Collect workflow: ingest curated RSS sources, keep the last 7 days, write a digest.

Search  -> sources.yaml (the curated source list)
Collect -> this script (fetch, parse, filter, store)
Process -> weekly HTML/Markdown digest used to pick a discussion-post article
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import feedparser
import requests
import yaml
from dateutil import parser as date_parser

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
CONFIG_PATH = ROOT / "sources.yaml"
USER_AGENT = (
    "TechCollect/1.0 (+academic Collect workflow; "
    "weekly discussion-post curation)"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("collect")


@dataclass
class Article:
    id: str
    source_id: str
    source_name: str
    category: str
    title: str
    url: str
    published: str
    summary: str
    relevance_score: int
    collected_at: str

    def published_dt(self) -> datetime | None:
        if not self.published:
            return None
        try:
            dt = date_parser.parse(self.published)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, OverflowError, TypeError):
            return None


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def article_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self.chunks.append(data)

    def text(self) -> str:
        return unescape(" ".join("".join(self.chunks).split()))


def clean_text(value: str, limit: int = 420) -> str:
    if not value:
        return ""
    parser = _HTMLText()
    parser.feed(re.sub(r"<br\s*/?>", " ", value, flags=re.I))
    text = parser.text()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def parse_entry_date(entry: Any) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, field, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    for field in ("published", "updated"):
        raw = entry.get(field)
        if not raw:
            continue
        try:
            dt = date_parser.parse(str(raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, OverflowError, TypeError):
            continue
    return None


def score_article(title: str, summary: str, keywords: list[str]) -> int:
    haystack = f"{title} {summary}".lower()
    return sum(1 for keyword in keywords if keyword.lower() in haystack)


def fetch_feed(url: str) -> feedparser.FeedParserDict:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"},
        timeout=25,
    )
    response.raise_for_status()
    return feedparser.parse(response.content)


def collect_source(
    source: dict[str, Any],
    cutoff: datetime,
    keywords: list[str],
    max_articles: int,
    collected_at: str,
) -> tuple[list[Article], dict[str, Any]]:
    status: dict[str, Any] = {
        "id": source["id"],
        "name": source["name"],
        "ok": False,
        "fetched": 0,
        "kept": 0,
        "error": None,
    }
    try:
        feed = fetch_feed(source["rss"])
        if feed.bozo and not feed.entries:
            raise RuntimeError(str(getattr(feed, "bozo_exception", "invalid feed")))
        kept: list[Article] = []
        for entry in feed.entries:
            status["fetched"] += 1
            url = (entry.get("link") or "").strip()
            title = clean_text(entry.get("title") or "Untitled", limit=240)
            if not url:
                continue
            published_dt = parse_entry_date(entry)
            if published_dt is not None and published_dt < cutoff:
                continue
            summary = clean_text(
                entry.get("summary") or entry.get("description") or "",
            )
            article = Article(
                id=article_id(url),
                source_id=source["id"],
                source_name=source["name"],
                category=source["category"],
                title=title,
                url=url,
                published=published_dt.isoformat() if published_dt else "",
                summary=summary,
                relevance_score=score_article(title, summary, keywords),
                collected_at=collected_at,
            )
            kept.append(article)
        kept.sort(key=lambda item: (item.published_dt() or cutoff, item.relevance_score), reverse=True)
        kept = kept[:max_articles]
        status["kept"] = len(kept)
        status["ok"] = True
        return kept, status
    except Exception as exc:  # noqa: BLE001 - surface feed failures in the digest
        status["error"] = str(exc)
        log.warning("Failed to collect %s: %s", source["name"], exc)
        return [], status


def merge_articles(existing: list[Article], incoming: list[Article]) -> list[Article]:
    by_id = {item.id: item for item in existing}
    for article in incoming:
        previous = by_id.get(article.id)
        if previous is None or article.relevance_score >= previous.relevance_score:
            by_id[article.id] = article
    return list(by_id.values())


def load_existing(path: Path) -> list[Article]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Article(**item) for item in payload.get("articles", [])]


def within_window(articles: list[Article], cutoff: datetime) -> list[Article]:
    recent = []
    for article in articles:
        published = article.published_dt()
        if published is None or published >= cutoff:
            recent.append(article)
    recent.sort(
        key=lambda item: (
            item.relevance_score,
            item.published_dt() or cutoff,
        ),
        reverse=True,
    )
    return recent


def write_json(path: Path, articles: list[Article], meta: dict[str, Any]) -> None:
    payload = {
        **meta,
        "article_count": len(articles),
        "articles": [asdict(item) for item in articles],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(path: Path, articles: list[Article]) -> None:
    fieldnames = [
        "source_name",
        "category",
        "published",
        "relevance_score",
        "title",
        "url",
        "summary",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for article in articles:
            writer.writerow({name: getattr(article, name) for name in fieldnames})


def render_markdown(
    articles: list[Article],
    statuses: list[dict[str, Any]],
    generated_at: datetime,
    window_days: int,
) -> str:
    lines = [
        f"# Weekly tech digest — last {window_days} days",
        "",
        f"Generated: {generated_at.strftime('%A, %B %d, %Y at %H:%M UTC')}",
        f"Articles in window: **{len(articles)}**",
        "",
        "## Source health",
        "",
        "| Source | Status | Fetched | Kept | Notes |",
        "|---|---|---:|---:|---|",
    ]
    for status in statuses:
        mark = "OK" if status["ok"] else "FAILED"
        notes = status.get("error") or ""
        lines.append(
            f"| {status['name']} | {mark} | {status['fetched']} | {status['kept']} | {notes} |"
        )
    lines += ["", "## Ranked articles", ""]
    if not articles:
        lines.append("_No articles collected in the current window._")
        return "\n".join(lines) + "\n"

    grouped: dict[str, list[Article]] = {}
    for article in articles:
        grouped.setdefault(article.source_name, []).append(article)

    for source_name, group in grouped.items():
        lines.append(f"### {source_name}")
        lines.append("")
        for article in group:
            published = article.published_dt()
            when = published.strftime("%b %d, %Y") if published else "Date unavailable"
            lines.append(f"- **[{article.title}]({article.url})**")
            lines.append(f"  - {when} · relevance {article.relevance_score} · {article.category}")
            if article.summary:
                lines.append(f"  - {article.summary}")
        lines.append("")
    return "\n".join(lines)


def render_html(
    articles: list[Article],
    statuses: list[dict[str, Any]],
    generated_at: datetime,
    window_days: int,
    sources: list[dict[str, Any]],
) -> str:
    ok_count = sum(1 for status in statuses if status["ok"])
    cards = []
    for article in articles:
        published = article.published_dt()
        when = published.strftime("%b %d, %Y") if published else "Date unavailable"
        cards.append(
            f"""
            <article class="card">
              <div class="meta">
                <span class="source">{escape(article.source_name)}</span>
                <span class="dot">·</span>
                <span>{escape(when)}</span>
                <span class="score">rel {article.relevance_score}</span>
              </div>
              <h3><a href="{escape(article.url)}" target="_blank" rel="noopener">{escape(article.title)}</a></h3>
              <p>{escape(article.summary)}</p>
            </article>
            """
        )
    if not cards:
        cards.append('<p class="empty">No articles collected in the current window.</p>')

    health_rows = []
    for status in statuses:
        cls = "ok" if status["ok"] else "fail"
        note = escape(status.get("error") or "Healthy")
        health_rows.append(
            f"<tr class='{cls}'><td>{escape(status['name'])}</td>"
            f"<td>{'OK' if status['ok'] else 'FAILED'}</td>"
            f"<td>{status['fetched']}</td><td>{status['kept']}</td>"
            f"<td>{note}</td></tr>"
        )

    source_pills = "".join(
        f'<span class="pill">{escape(item["name"])}</span>' for item in sources
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Weekly tech digest · Collect workflow</title>
  <style>
    :root {{
      --bg: #0f172a;
      --panel: #1e293b;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --ok: #34d399;
      --fail: #fb7185;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    header, main {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
    header {{
      padding-top: 40px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 2rem; }}
    .lede {{ color: var(--muted); margin-bottom: 20px; }}
    .stats {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }}
    .stat, .pill {{
      background: var(--panel);
      border: 1px solid #334155;
      border-radius: 999px;
      padding: 8px 14px;
      color: var(--muted);
    }}
    .stat strong {{ color: var(--accent); }}
    .pills {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 28px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border-radius: 12px;
      overflow: hidden;
      margin-bottom: 28px;
    }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #334155; }}
    th {{ color: var(--muted); font-weight: 600; font-size: 0.85rem; }}
    tr.ok td:nth-child(2) {{ color: var(--ok); }}
    tr.fail td:nth-child(2) {{ color: var(--fail); }}
    .card {{
      background: var(--panel);
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 16px 18px;
      margin-bottom: 12px;
    }}
    .meta {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 6px; }}
    .score {{
      float: right;
      color: var(--accent);
    }}
    a {{ color: #7dd3fc; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    h2 {{ margin-top: 8px; }}
    .empty {{ color: var(--muted); }}
  </style>
</head>
<body>
  <header>
    <h1>Weekly tech digest</h1>
    <p class="lede">Collect workflow output for discussion-post curation. Window: last {window_days} days.</p>
    <div class="stats">
      <div class="stat">Generated <strong>{generated_at.strftime("%b %d, %Y %H:%M UTC")}</strong></div>
      <div class="stat">Sources healthy <strong>{ok_count}/{len(statuses)}</strong></div>
      <div class="stat">Articles kept <strong>{len(articles)}</strong></div>
    </div>
    <div class="pills">{source_pills}</div>
  </header>
  <main>
    <h2>Source health</h2>
    <table>
      <thead><tr><th>Source</th><th>Status</th><th>Fetched</th><th>Kept</th><th>Notes</th></tr></thead>
      <tbody>
        {''.join(health_rows)}
      </tbody>
    </table>
    <h2>Ranked articles</h2>
    {''.join(cards)}
  </main>
</body>
</html>
"""


def write_run_log(path: Path, statuses: list[dict[str, Any]], article_count: int) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    lines = [f"{stamp}  articles={article_count}"]
    for status in statuses:
        state = "OK" if status["ok"] else "FAIL"
        lines.append(
            f"  {state:4}  {status['name']}: fetched={status['fetched']} kept={status['kept']} {status.get('error') or ''}"
        )
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def run(window_days: int | None = None, collect_only: bool = False, digest_only: bool = False) -> int:
    config = load_config()
    days = window_days or int(config.get("window_days", 7))
    keywords = list(config.get("keyword_boost", []))
    max_articles = int(config.get("max_articles_per_source", 20))
    sources = config["sources"]
    if len(sources) < 5:
        raise SystemExit("Need at least 5 sources in sources.yaml")

    DATA_DIR.mkdir(exist_ok=True)
    DOCS_DIR.mkdir(exist_ok=True)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    json_path = DATA_DIR / "articles.json"
    csv_path = DATA_DIR / "articles.csv"
    md_path = DATA_DIR / "weekly_digest.md"
    html_path = DATA_DIR / "weekly_digest.html"
    log_path = DATA_DIR / "collect.log"

    statuses: list[dict[str, Any]] = []
    incoming: list[Article] = []
    if not digest_only:
        collected_at = now.isoformat()
        for source in sources:
            log.info("Collecting %s", source["name"])
            articles, status = collect_source(
                source, cutoff, keywords, max_articles, collected_at
            )
            incoming.extend(articles)
            statuses.append(status)
            log.info(
                "  %s: fetched=%s kept=%s",
                "OK" if status["ok"] else "FAIL",
                status["fetched"],
                status["kept"],
            )
        existing = load_existing(json_path)
        merged = merge_articles(existing, incoming)
        recent = within_window(merged, cutoff)
        write_json(
            json_path,
            recent,
            {
                "generated_at": now.isoformat(),
                "window_days": days,
                "source_count": len(sources),
                "statuses": statuses,
            },
        )
        write_csv(csv_path, recent)
        write_run_log(log_path, statuses, len(recent))
    else:
        recent = within_window(load_existing(json_path), cutoff)
        payload = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {}
        statuses = payload.get("statuses", [])

    if collect_only:
        log.info("Collect finished with %s articles", len(recent))
        return 0

    md_path.write_text(render_markdown(recent, statuses, now, days), encoding="utf-8")
    html_path.write_text(render_html(recent, statuses, now, days, sources), encoding="utf-8")
    docs_digest = DOCS_DIR / "weekly_digest.html"
    docs_digest.write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")
    log.info("Digest written: %s (%s articles)", html_path, len(recent))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the course Collect workflow.")
    parser.add_argument("--days", type=int, default=None, help="Lookback window in days (default: 7)")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--digest-only", action="store_true")
    args = parser.parse_args()
    return run(window_days=args.days, collect_only=args.collect_only, digest_only=args.digest_only)


if __name__ == "__main__":
    sys.exit(main())
