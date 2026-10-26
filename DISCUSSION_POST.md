# Discussion post — Collect workflow

Each week this course asks for a review of one technology article published in the last seven days. That only works if I already have a Collect layer in place — a short list of sources I trust, and a repeatable way to pull new items from them instead of starting from a blank search every Sunday.

## Sources I will monitor

I chose seven sources on purpose: independent journalism, a practitioner aggregator, a professional society, and one company blog. That mix keeps me from seeing only vendor announcements or only headline recaps.

1. **MIT Technology Review** — Independent tech journalism. It is slower than a news ticker and usually explains why a result or product matters. That depth is a better starting point for a discussion post than a launch recap.

2. **Ars Technica** — Technical journalism with enough engineering detail to test claims. If a story is about a model, a chip, or a security flaw, I want the version that shows the mechanism, not only the announcement.

3. **TechCrunch** — Industry and startup news. Funding, acquisitions, and platform strategy are part of the technology story, and this source covers that side faster than research magazines.

4. **IEEE Spectrum** — The IEEE’s engineering magazine. It adds hardware, energy, and robotics coverage from a professional-engineering point of view, which consumer tech sites often skip.

5. **Hacker News** — News aggregator (`hnrss.org/frontpage`). It is how I catch papers, independent blogs, and practitioner debates that never reach a homepage. I am not treating the comments as a source of record; I am using the front page as a pointer.

6. **Google AI Blog** — Company research blog. Primary-source posts let me compare a vendor’s own write-up with independent coverage from the journalism sources above.

7. **The Verge** — Consumer tech and policy. Useful for regulation, platform rules, and how a technology actually shows up for users.

I kept the list at seven rather than twenty so I can actually read the digest. If a feed goes stale, I replace it during the monthly source review instead of letting the pile grow.

## Collect workflow and architecture

I built an automated RSS collector in the `Setup Collect` folder instead of relying on a ChatGPT tab and memory.

**Search** is the curated catalog in `sources.yaml`: name, homepage, RSS URL, category, and a one-sentence reason each source is in the set.

**Collect** is `collect.py`, wrapped by `run_collect.sh` and scheduled with a macOS `launchd` job (`schedule/com.sanjay.techcollect.plist`) at **7:00 AM daily**. Each run:

1. Fetches every feed with a dedicated User-Agent.
2. Parses title, URL, published date, and summary.
3. Drops items older than seven days.
4. Scores remaining items against a small AI/tech keyword list so the digest is not just reverse-chronological noise.
5. Deduplicates by article URL.
6. Writes `data/articles.json`, `data/articles.csv`, `data/weekly_digest.html`, and a run log.

**Process** stays human. I do not auto-summarize articles into the discussion post. The digest is a briefing. I still open the piece, check the date, and write the review myself.

```text
sources.yaml → collect.py → RSS feeds → 7-day filter → JSON/CSV
                                           ↓
                                   weekly_digest.html
                                           ↓
                          Wednesday skim → Sunday pick → discussion post
```

A browser view of the architecture is in `docs/architecture.html`. Screenshots are in `docs/screenshots/`: the architecture diagram, the first live digest (7/7 sources healthy, 89 in-window articles on 25 Oct 2026), and the collector run output.

## How often I will review it

- **Daily, automated:** collect and refresh the 7-day digest.
- **Wednesday, ~15 minutes:** skim the digest and star two or three candidates.
- **Sunday, ~45–60 minutes:** confirm the chosen article is from the last seven days, read it, and write the post.
- **Monthly:** review the source list, drop dead feeds, and add a replacement if the mix has gone stale.

Daily collection is there so a busy Saturday does not leave me with nothing in-window on Sunday. The actual editorial work stays twice a week, which is sustainable for the rest of the course.
