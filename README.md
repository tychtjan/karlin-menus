# Karlin Lunch Menus

Automated daily lunch menu fetcher for 3 restaurants in Prague Karlin.

## How it works

```
GitHub Actions (8:00 UTC, Mon-Fri)
  fetch_menus.py fetches menus from 3 sources
  saves structured JSON to menus/

Claude AI scheduled trigger (8:30 UTC, Mon-Fri)
  reads menus/*.json
  formats and posts to Slack
```

## Restaurants

| Restaurant | Source |
|---|---|
| Pivo Karlin | [menicka.cz](https://www.menicka.cz/6912-pivo-karlin.html) |
| Diego Pivni Bar | [menicka.cz](https://www.menicka.cz/7191-diego-pivni-bar.html) |
| Tankovna Karlin | [Sanity CMS API](https://www.tankovnakarlin.cz/) |

## Files

- `fetch_menus.py` — Python script that fetches and parses menus into JSON
- `menus/*.json` — Latest fetched menu data (auto-updated by CI)
- `.github/workflows/fetch-menus.yml` — GitHub Actions cron workflow
