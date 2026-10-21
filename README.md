# Karlín Lunch Menus

Daily lunch menu bot for 6 restaurants near Block Karlín, Prague. Posts to Slack in Czech and English.

## How it works

```
GitHub Actions (10:00 CEST, Mon-Fri)
  ├─ fetch_menus.py — scrapes 6 restaurant sources → menus/*.json
  ├─ commits updated JSON files
  └─ post_menus.py — posts Czech + English (dish names translated via Claude) to Slack as table blocks,
     with a plain-text fallback if Slack rejects the blocks
```

## Restaurants

| Restaurant | Source | Method |
|---|---|---|
| Pivo Karlín | [menicka.cz](https://www.menicka.cz/6912-pivo-karlin.html) | HTML scraping |
| Diego Pivní Bar | [menicka.cz](https://www.menicka.cz/7191-diego-pivni-bar.html) | HTML scraping |
| Tankovna Karlín | [tankovnakarlin.cz](https://www.tankovnakarlin.cz/) | Sanity CMS API |
| San Carlo | [sancarlo.cz](https://sancarlo.cz/menu.png) | PNG → Claude Vision |
| Dvorek Karlín | [menicka.cz](https://www.menicka.cz/2427-dvorek-karlin.html) | HTML scraping |
| Jídlovice Karlín | [jidlovice.cz](https://www.jidlovice.cz/karlin/) | REST API |

## Files

- `fetch_menus.py` — Fetches and parses menus into JSON
- `post_menus.py` — Posts to Slack channels and updates canvases
- `menu_format.py` — Slack text and canvas Markdown (tables) builders, CZ/EN labels
- `menu_translate.py` — Translates dish names to English and validates the reply shape
- `slack_blocks.py` — Slack `table` block builders and message chunking
- `spike_table_blocks.py` — One-off script that probes which table block shapes Slack accepts (test channel only)
- `menus/*.json` — Latest fetched menu data (auto-updated by CI)
- `.github/workflows/fetch-menus.yml` — GitHub Actions workflow

## Secrets

| Secret | Purpose |
|---|---|
| `SLACK_BOT_TOKEN` | Slack API bot token for posting messages and updating canvases |
| `CLAUDE_API_KEY` | Anthropic API key for English translation and San Carlo menu OCR |

## Manual run

```bash
gh workflow run "Fetch Daily Menus"                    # production
gh workflow run "Fetch Daily Menus" -f test_mode=true  # test channel
```
