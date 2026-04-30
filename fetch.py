#!/usr/bin/env python3
"""Fetch GitHub contribution calendar by scraping the public profile.

No authentication required. Counts match the public profile UI exactly,
including private contributions when "Include private contributions on
my profile" is enabled in GitHub settings.

Per-day counts are floored against the previous snapshot — if scraping
breaks or returns less in the future, recorded counts cannot regress.
"""

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

DIR = Path(__file__).resolve().parent
CONFIG = json.loads((DIR / "config.json").read_text())
OUT = DIR / "contributions.json"

USER_AGENT = "gitgud-contributions-fetcher"
COUNT_RE = re.compile(r"^(\d+|No)\b", re.IGNORECASE)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


class CalendarParser(HTMLParser):
    """Extract day cells (id -> date) and tooltip text (for-id -> text)."""

    def __init__(self):
        super().__init__()
        self.day_id_to_date: dict[str, str] = {}
        self.tooltips: dict[str, str] = {}
        self._tooltip_for: str | None = None
        self._tooltip_parts: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "td" and "ContributionCalendar-day" in (a.get("class") or ""):
            cell_id = a.get("id")
            date = a.get("data-date")
            if cell_id and date:
                self.day_id_to_date[cell_id] = date
        elif tag == "tool-tip":
            for_attr = a.get("for")
            if for_attr:
                self._tooltip_for = for_attr
                self._tooltip_parts = []

    def handle_data(self, data):
        if self._tooltip_parts is not None:
            self._tooltip_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "tool-tip" and self._tooltip_for is not None:
            self.tooltips[self._tooltip_for] = "".join(self._tooltip_parts or "").strip()
            self._tooltip_for = None
            self._tooltip_parts = None


def parse_count(tooltip_text: str) -> int:
    m = COUNT_RE.match(tooltip_text)
    if not m:
        raise ValueError(f"unparseable tooltip: {tooltip_text!r}")
    val = m.group(1)
    return 0 if val.lower() == "no" else int(val)


def fetch_year_calendar(username: str, year: int) -> list[dict]:
    """Returns [{date, contributionCount}, ...] sorted by date, restricted to `year`."""
    url = f"https://github.com/users/{username}/contributions?to={year}-12-31"
    parser = CalendarParser()
    parser.feed(fetch(url))

    if not parser.day_id_to_date:
        raise RuntimeError(f"no day cells parsed for {year}; page structure may have changed")

    days = []
    for cell_id, date in parser.day_id_to_date.items():
        if not date.startswith(f"{year}-"):
            continue
        text = parser.tooltips.get(cell_id)
        if text is None:
            raise RuntimeError(f"day {date} (id {cell_id}) has no matching tool-tip")
        days.append({"date": date, "contributionCount": parse_count(text)})

    if not days:
        raise RuntimeError(f"no days for {year} after filtering (parsed {len(parser.day_id_to_date)} cells)")

    days.sort(key=lambda d: d["date"])
    return days


def get_account_created_year(username: str) -> int:
    data = json.loads(fetch(f"https://api.github.com/users/{username}"))
    return int(data["created_at"][:4])


def merge_calendar(existing: list[dict], scraped: list[dict]) -> list[dict]:
    """Per-day floor: each day's count cannot drop below its previously-saved value."""
    by_date = {d["date"]: d["contributionCount"] for d in existing}
    for d in scraped:
        by_date[d["date"]] = max(d["contributionCount"], by_date.get(d["date"], 0))
    return [{"date": d, "contributionCount": c} for d, c in sorted(by_date.items())]


def main():
    username = CONFIG["username"]
    existing = json.loads(OUT.read_text()) if OUT.exists() else {}
    existing_years = {y["year"]: y for y in existing.get("years", [])}

    try:
        start_year = get_account_created_year(username)
    except Exception as e:
        if existing_years:
            start_year = min(existing_years)
            print(f"warn: account creation lookup failed ({e}); using {start_year} from existing data")
        else:
            print(f"error: cannot determine start year and no existing data: {e}", file=sys.stderr)
            sys.exit(1)

    now = datetime.now(timezone.utc)
    fetched_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_year = max(now.year, max(existing_years) if existing_years else now.year)

    print(f"Fetching contribution calendar for {username} ({start_year}–{end_year})...")

    new_years = []
    failed_years = []
    for year in range(start_year, end_year + 1):
        print(f"  {year}...", end="", flush=True)
        try:
            scraped = fetch_year_calendar(username, year)
        except Exception as e:
            failed_years.append(year)
            if year in existing_years:
                new_years.append(existing_years[year])
                kept = existing_years[year]["totals"]["contributions"]
                print(f" FAILED ({e}); kept existing ({kept})")
            else:
                print(f" FAILED ({e}); no prior data — skipping year")
            continue

        prev_cal = existing_years.get(year, {}).get("calendar", [])
        merged = merge_calendar(prev_cal, scraped)
        total = sum(d["contributionCount"] for d in merged)
        new_years.append({
            "year": year,
            "totals": {"contributions": total},
            "calendar": merged,
        })
        print(f" {total} contributions ({len(merged)} days)")

    if not new_years:
        print("error: no year data to save", file=sys.stderr)
        sys.exit(1)

    new_total = sum(y["totals"]["contributions"] for y in new_years)
    existing_total = sum(y["totals"]["contributions"] for y in existing.get("years", []))
    if existing_total and new_total < existing_total:
        # Per-day floor should make this impossible; this gate defends against
        # bugs in merge logic itself.
        print(
            f"error: total regressed ({existing_total} -> {new_total}); refusing to write",
            file=sys.stderr,
        )
        sys.exit(1)

    output = {"user": username, "fetched_at": fetched_at, "years": new_years}
    OUT.write_text(json.dumps(output, indent=2))

    size = OUT.stat().st_size
    total_days = sum(len(y["calendar"]) for y in new_years)
    print(f"\nSaved to {OUT}")
    print(f"Size: {size / 1000:.1f} KB")
    print(f"Years: {len(new_years)} | Calendar days: {total_days} | Total contributions: {new_total}")
    if failed_years:
        print(f"warn: scraping failed for years: {failed_years}", file=sys.stderr)


if __name__ == "__main__":
    main()
