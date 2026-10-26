# Setup Collect

Automated **Collect** workflow for weekly technology discussion posts.

The course requires one tech article from the **last 7 days**. This folder is the collection layer: a curated source list, a daily RSS ingest, and a ranked digest used to pick the article.

**Repository:** [github.com/sstephen-2102/setup-collect](https://github.com/sstephen-2102/setup-collect)  
**Full write-up:** [FINAL_REPORT.md](FINAL_REPORT.md)

## Quick start

```bash
cd "/Users/sanjayvarghese/Cursor Projects/Setup Collect"
chmod +x run_collect.sh
./run_collect.sh
open data/weekly_digest.html
```

## What to submit / point reviewers at

| File | What it is |
|---|---|
| [FINAL_REPORT.md](FINAL_REPORT.md) | End-to-end report: repo, design, frequency, implementation |
| [DISCUSSION_POST.md](DISCUSSION_POST.md) | Course discussion text: sources, why, architecture, frequency |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Technical architecture, data flow, and review cadence |
| [sources.yaml](sources.yaml) | The seven monitored sources |
| [docs/architecture.html](docs/architecture.html) | Visual architecture diagram |
| [data/weekly_digest.html](data/weekly_digest.html) | Latest live digest (created after the first run) |
| [docs/screenshots/](docs/screenshots/) | Screenshots of the digest and architecture page |

## Layout

```text
Setup Collect/
├── sources.yaml              curated Search catalog
├── collect.py                Collect engine
├── run_collect.sh            venv bootstrap + runner
├── requirements.txt
├── FINAL_REPORT.md
├── ARCHITECTURE.md
├── DISCUSSION_POST.md
├── schedule/                 daily 07:00 launchd job
├── data/                     JSON, CSV, HTML digest, logs
└── docs/                     architecture page + screenshots
```

## Schedule

See [schedule/README.md](schedule/README.md). Default review rhythm:

- Daily 07:00 — automated collect
- Wednesday — 15-minute skim
- Sunday — choose the article and write the post
- Monthly — source-list maintenance
