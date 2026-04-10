# .gitgud

Lifetime GitHub contribution heatmap. Fetches daily contribution history via the GraphQL API and renders a static HTML page with all years side by side.

**[Live](https://caseprince.github.io/.gitgud/)**

## Setup

1. Edit `config.json` with your GitHub username
2. Install the [GitHub CLI](https://cli.github.com/) and authenticate (`gh auth login`)
3. Run `python fetch.py` then `python render.py`
4. Open `index.html`

## GitHub Actions

A nightly workflow updates the data and commits. Requires a `GH_PAT` repo secret with `read:user` scope (add `repo` scope to include private contribution details).

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
