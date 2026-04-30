# .gitgud

Lifetime GitHub contribution heatmap. Scrapes the public profile contribution calendar (no auth required) and renders a static HTML page with all years side by side. Per-day counts are floored against the previous snapshot, so a future scraper break can never reduce recorded contributions.

Live on Github Pages: https://caseprince.github.io/.gitgud/

## Setup

1. Edit `config.json` with your GitHub username
2. Run `python fetch.py` then `python render.py`
3. Open `index.html`

Counts include private contributions if you've enabled "Include private contributions on my profile" in your GitHub profile settings.

## GitHub Actions

A nightly workflow updates the data and commits. No secrets required — `GITHUB_TOKEN` granted by `permissions: contents: write` is enough to push.

## Config

```json
{
  "username": "caseprince",
  "cell_size": 10,
  "gap": 2,
  "year_gap": 6,
  "color": "46, 160, 67"
}
```
