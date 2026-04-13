#!/usr/bin/env python3
"""Generate HTML contribution heatmap from contributions.json."""

import calendar as cal
import json
from html import escape as html_escape
import subprocess
from datetime import date, timedelta
from pathlib import Path

DIR = Path(__file__).resolve().parent
CONFIG = json.loads((DIR / "config.json").read_text())
DATA = DIR / "contributions.json"
OUT = DIR / "index.html"

CELL_SIZE = CONFIG.get("cell_size", 10)
GAP = CONFIG.get("gap", 2)
YEAR_GAP = CONFIG.get("year_gap", 6)
GREEN = CONFIG.get("color", "46, 160, 67")
# Outer radius so the content box (after padding + background-clip) matches this corner radius.
CELL_RADIUS = 2


def ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def tooltip(count: int, d: date) -> str:
    month = cal.month_name[d.month]
    day = ordinal(d.day)
    if count == 0:
        return f"No contributions on {month} {day}."
    if count == 1:
        return f"1 contribution on {month} {day}."
    return f"{count} contributions on {month} {day}."


def repo_url() -> str:
    """Derive the GitHub HTTPS URL from the git remote."""
    result = subprocess.run(
        ["git", "-C", str(DIR), "remote", "get-url", "origin"],
        capture_output=True, text=True,
    )
    url = result.stdout.strip()
    # Normalise ssh or .git suffix to plain https
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url[len("git@github.com:"):]
    return url.removesuffix(".git")


def main():
    data = json.loads(DATA.read_text())
    fetched = date.fromisoformat(data["fetched_at"][:10])
    username = data["user"]
    profile_url = f"https://github.com/{username}"
    this_repo = repo_url()

    # Skip years with zero contributions
    active_years = [yd for yd in data["years"] if yd["totals"]["contributions"] > 0]

    # Lifetime total
    lifetime = sum(yd["totals"]["contributions"] for yd in active_years)

    # Collect all non-zero counts to compute intensity quartiles
    all_counts = sorted(
        day["contributionCount"]
        for yd in active_years
        for day in yd["calendar"]
        if day["contributionCount"] > 0
    )
    n = len(all_counts)
    if n > 0:
        q1 = all_counts[n // 4]
        q2 = all_counts[n // 2]
        q3 = all_counts[3 * n // 4]
    else:
        q1 = q2 = q3 = 1

    def level(count: int) -> int:
        if count == 0:
            return 0
        if count <= q1:
            return 1
        if count <= q2:
            return 2
        if count <= q3:
            return 3
        return 4

    html_years = []

    for year_data in active_years:
        year = year_data["year"]
        jan1 = date(year, 1, 1)
        jan1_wd = jan1.weekday()

        counts = {}
        for day in year_data["calendar"]:
            counts[day["date"]] = day["contributionCount"]

        last = fetched if year == fetched.year else date(year, 12, 31)
        cells = []
        d = jan1
        while d <= last:
            doy = (d - jan1).days
            row = (doy + jan1_wd) // 7 + 1
            col = d.weekday() + 1
            count = counts.get(d.isoformat(), 0)
            lvl = level(count)
            tip = html_escape(tooltip(count, d))
            cells.append(
                f'<div class="c{lvl} day-cell" style="grid-row:{row};grid-column:{col}" '
                f'data-tip="{tip}" aria-label="{tip}"></div>'
            )
            d += timedelta(days=1)

        html_years.append(
            f'<div class="year-col"><span class="label">{year}</span>\n'
            f'<div class="year">\n' + "\n".join(cells) + "\n</div></div>"
        )

    html = f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{username} contributions</title>
<style>
:root {{ color-scheme: dark; }}
@media (prefers-color-scheme: dark) {{
  body {{ background: #0d1117; color: rgba(255, 255, 255, 0.7); }}
  .c0 {{ background: rgba(255, 255, 255, 0.05); }}
  a {{ color: rgba(255, 255, 255, 0.85); }}
  a:hover {{ color: #fff; }}
  .day-cell:hover {{
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.35);
  }}
}}
@media (prefers-color-scheme: light) {{
  body {{ background: #ffffff; color: rgba(0, 0, 0, 0.7); }}
  .c0 {{ background: rgba(0, 0, 0, 0.06); }}
  a {{ color: rgba(0, 0, 0, 0.85); }}
  a:hover {{ color: #000; }}
  .day-cell:hover {{
    box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.22);
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  padding: 24px;
  min-height: 100vh;
  display: flex;
  justify-content: center;
  font-family: "SF Mono", "Cascadia Code", "Fira Code", "JetBrains Mono", monospace;
}}
a {{ text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
main {{
  max-width: 100%;
}}
header {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 24px;
  padding-bottom: 20px;
}}
.scroll {{
  overflow-x: auto;
  padding-bottom: 24px;
}}
h1 {{
  font-weight: 300;
  font-size: 20px;
  letter-spacing: 0.05em;
  margin: 0;
  white-space: nowrap;
}}
h2 {{
  font-weight: 300;
  font-size: 14px;
  letter-spacing: 0.05em;
  margin: 0;
  white-space: nowrap;
  opacity: 0.6;
}}
.grid {{
  display: flex;
  gap: {YEAR_GAP}px;
  flex-shrink: 0;
}}
.year-col {{
  display: flex;
  flex-direction: column;
}}
.label {{
  font-size: 10px;
  font-weight: 400;
  letter-spacing: 0.03em;
  padding-bottom: 4px;
  opacity: 0.5;
}}
.year {{
  display: grid;
  grid-template-columns: repeat(7, {CELL_SIZE + GAP}px);
  grid-auto-rows: {CELL_SIZE + GAP}px;
  gap: 0;
}}
.year > div {{
  border-radius: {CELL_RADIUS + GAP / 2:g}px;
  padding: {GAP / 2:g}px;
  background-clip: content-box;
}}
.c1 {{ background: rgba({GREEN}, 0.2); }}
.c2 {{ background: rgba({GREEN}, 0.4); }}
.c3 {{ background: rgba({GREEN}, 0.7); }}
.c4 {{ background: rgba({GREEN}, 1.0); }}
.day-cell {{ cursor: default; }}
#tip {{
  position: fixed;
  z-index: 1080;
  left: 0;
  top: 0;
  max-width: min(280px, calc(100vw - 16px));
  padding: 0.25rem 0.5rem;
  font-size: 0.8125rem;
  font-weight: 400;
  line-height: 1.4;
  color: #fff;
  text-align: center;
  background-color: #212529;
  border-radius: 0.25rem;
  box-shadow: 0 0.125rem 0.25rem rgba(0, 0, 0, 0.15);
  pointer-events: none;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.12s ease;
}}
#tip.show {{
  opacity: 1;
  visibility: visible;
}}
</style>
</head>
<body>
<main>
<header>
  <h1><a href="{profile_url}">@{username}</a>: {lifetime:,} contributions</h1>
  <h2><a href="{this_repo}">.gitgud</a></h2>
</header>
<div class="scroll">
  <div class="grid">
{chr(10).join(html_years)}
  </div>
</div>
</main>
<div id="tip" role="tooltip" aria-hidden="true"></div>
<script>
(function () {{
  var scroll = document.querySelector('.scroll');
  var grid = document.querySelector('.grid');
  var tip = document.getElementById('tip');
  if (!scroll || !grid || !tip) return;

  function hide() {{
    tip.classList.remove('show');
    tip.setAttribute('aria-hidden', 'true');
  }}

  function show(el) {{
    var text = el.getAttribute('data-tip');
    if (!text) return;
    tip.textContent = text;
    tip.classList.add('show');
    tip.removeAttribute('aria-hidden');

    requestAnimationFrame(function () {{
      var r = el.getBoundingClientRect();
      var tr = tip.getBoundingClientRect();
      var margin = 6;
      var pad = 8;
      var x = r.left + r.width / 2 - tr.width / 2;
      var y = r.top - tr.height - margin;
      if (y < pad) y = r.bottom + margin;
      x = Math.max(pad, Math.min(x, window.innerWidth - tr.width - pad));
      tip.style.left = x + 'px';
      tip.style.top = y + 'px';
    }});
  }}

  grid.addEventListener('mouseover', function (e) {{
    var cell = e.target.closest('.day-cell');
    if (cell) show(cell);
  }});
  grid.addEventListener('mouseout', function (e) {{
    var cell = e.target.closest('.day-cell');
    if (!cell) return;
    var related = e.relatedTarget;
    if (related && cell.contains(related)) return;
    var toCell = related && related.closest && related.closest('.day-cell');
    if (toCell) {{ show(toCell); return; }}
    hide();
  }});
  scroll.addEventListener('scroll', hide);
  document.addEventListener('scroll', hide, true);
  window.addEventListener('blur', hide);

  scroll.scrollLeft = 1e9;
}})();
</script>
</body>
</html>"""

    OUT.write_text(html)
    size = OUT.stat().st_size
    yr_range = f"{active_years[0]['year']}\u2013{active_years[-1]['year']}"
    print(f"Generated {OUT} ({size / 1000:.1f} KB)")
    print(f"Years: {len(active_years)} ({yr_range}) | Lifetime: {lifetime:,} contributions")
    print(f"Intensity quartiles: q1={q1} q2={q2} q3={q3} (from {n} active days)")


if __name__ == "__main__":
    main()
