#!/usr/bin/env python3
"""Post daily lunch menus to Slack channels and update canvases."""

import json
import os
import sys
from datetime import date

import anthropic
import requests

MENUS_DIR = os.path.join(os.path.dirname(__file__), "menus")
SLACK_TOKEN = os.environ["SLACK_BOT_TOKEN"]
CLAUDE_API_KEY = os.environ["CLAUDE_API_KEY"]

CZECH_DAYS = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"]

# Test mode: send everything to a single test channel, skip canvases
TEST_MODE = os.environ.get("TEST_MODE", "").lower() in ("1", "true", "yes")
TEST_CHANNEL = "C0AG0MU6HD2"

# Channel and canvas IDs
CZ_CHANNEL = TEST_CHANNEL if TEST_MODE else "C0AP80K2ETZ"
CZ_CANVAS = "F0APQG2RWV8"
EN_CHANNEL = TEST_CHANNEL if TEST_MODE else "C0AQAJFNG8Z"
EN_CANVAS = "F0AQ1CDG0TE"

RESTAURANTS = [
    {"file": "pivo.json", "emoji": ":beer:", "name": "Pivo Karlín"},
    {"file": "diego.json", "emoji": ":hot_pepper:", "name": "Diego Pivní Bar"},
    {"file": "tankovna.json", "emoji": ":beers:", "name": "Tankovna Karlín"},
    {"file": "dvorek.json", "emoji": ":deciduous_tree:", "name": "Dvorek Karlín"},
    {"file": "jidlovice.json", "emoji": ":stew:", "name": "Jídlovice Karlín"},
]

DIVIDER = "───────────────────────────────────"


def load_menus():
    """Load all menu JSON files and validate dates."""
    today_str = date.today().strftime("%Y-%m-%d")
    menus = []
    for r in RESTAURANTS:
        filepath = os.path.join(MENUS_DIR, r["file"])
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") != today_str:
                data["available"] = False
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"date": today_str, "restaurant": r["name"], "available": False, "soup": None, "dishes": []}
        menus.append({**r, "data": data})
    return menus


def format_restaurant_mrkdwn(menu, soup_label="Polévka", currency="Kč"):
    """Format a single restaurant's menu in Slack mrkdwn."""
    data = menu["data"]
    lines = [f'{menu["emoji"]} *{menu["name"]}*']

    if not data.get("available"):
        lines.append("Menu dnes není k dispozici" if currency == "Kč" else "No menu available today")
        return "\n".join(lines)

    soup = data.get("soup")
    if soup:
        price_str = f" • *{soup['price']} {currency}*" if soup.get("price") else ""
        lines.append(f"_{soup_label}:_ {soup['name']}{price_str}")

    for i, dish in enumerate(data.get("dishes", []), 1):
        price_str = f" • *{dish['price']} {currency}*" if dish.get("price") else ""
        lines.append(f"{i}. {dish['name']}{price_str}")

    return "\n".join(lines)


def format_restaurant_canvas(menu, soup_label="Polévka", currency="Kč"):
    """Format a single restaurant's menu in canvas Markdown."""
    data = menu["data"]
    lines = [f'## {menu["emoji"]} {menu["name"]}', ""]

    if not data.get("available"):
        lines.append("Menu dnes není k dispozici" if currency == "Kč" else "No menu available today")
        return "\n".join(lines)

    soup = data.get("soup")
    if soup:
        price_str = f" • **{soup['price']} {currency}**" if soup.get("price") else ""
        lines.append(f"*{soup_label}:* {soup['name']}{price_str}")
        lines.append("")

    for i, dish in enumerate(data.get("dishes", []), 1):
        price_str = f" • **{dish['price']} {currency}**" if dish.get("price") else ""
        lines.append(f"{i}. {dish['name']}{price_str}")

    return "\n".join(lines)


def build_czech_message(menus, date_str):
    """Build the full Czech Slack message."""
    parts = [f":knife_fork_plate: *Obědová menu — {date_str}*", ""]
    for menu in menus:
        parts.append(DIVIDER)
        parts.append(format_restaurant_mrkdwn(menu, "Polévka", "Kč"))
        parts.append("")
    parts.append(DIVIDER)
    parts.append(f":bookmark: <https://gooddata.slack.com/docs/T02G0PHRH/{CZ_CANVAS}|Otevřít v canvasu>")
    return "\n".join(parts)


def build_czech_canvas(menus, date_str):
    """Build the full Czech canvas content."""
    parts = [f"# :knife_fork_plate: Obědová menu — {date_str}", ""]
    for menu in menus:
        parts.append(format_restaurant_canvas(menu, "Polévka", "Kč"))
        parts.append("")
    return "\n".join(parts)


def translate_to_english(czech_message):
    """Use Claude API to translate the Czech menu message to English."""
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": (
                "Translate this Czech lunch menu to English. "
                "Keep restaurant names as-is (they are proper nouns). "
                "Translate dish names naturally using common English food terms "
                "(e.g. 'svíčková' → 'Marinated beef sirloin with cream sauce'). "
                "Keep the exact same formatting (numbered lists, bullet style, emojis, dividers). "
                "Replace 'Kč' with 'CZK'. Replace 'Polévka' with 'Soup'. "
                "Replace 'Obědová menu' with 'Lunch Menus'. "
                "Replace 'Otevřít v canvasu' with 'Open in canvas'. "
                "Replace 'Menu dnes není k dispozici' with 'No menu available today'. "
                "Output ONLY the translated message, nothing else.\n\n"
                f"{czech_message}"
            ),
        }],
    )
    return response.content[0].text


def build_english_canvas(english_message):
    """Convert English Slack mrkdwn to canvas Markdown."""
    # Transform mrkdwn bold (*text*) to markdown bold (**text**)
    # and italic (_text_) to markdown italic (*text*)
    lines = english_message.split("\n")
    canvas_lines = []
    for line in lines:
        if line.startswith(":knife_fork_plate:"):
            # Title line: convert to H1
            title = line.replace(":knife_fork_plate: *", "# :knife_fork_plate: ").rstrip("*")
            canvas_lines.append(title)
        elif line.startswith(DIVIDER):
            continue  # skip dividers in canvas
        elif line.startswith(":bookmark:"):
            continue  # skip footer in canvas
        elif any(line.startswith(f"{e} *") for e in [":beer:", ":hot_pepper:", ":beers:", ":deciduous_tree:", ":stew:"]):
            # Restaurant header: convert to H2
            header = line.replace(" *", " ").rstrip("*")
            canvas_lines.append("")
            canvas_lines.append(f"## {header}")
            canvas_lines.append("")
        else:
            canvas_lines.append(line)
    return "\n".join(canvas_lines)


def slack_post_message(channel, text):
    """Post a message to a Slack channel."""
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {SLACK_TOKEN}", "Content-Type": "application/json"},
        json={"channel": channel, "text": text, "unfurl_links": False, "unfurl_media": False},
        timeout=30,
    )
    result = resp.json()
    if not result.get("ok"):
        print(f"ERROR posting to {channel}: {result.get('error')}")
        return False
    print(f"Posted to {channel}")
    return True


def slack_update_canvas(canvas_id, markdown):
    """Update a Slack canvas with new content."""
    resp = requests.post(
        "https://slack.com/api/canvases.edit",
        headers={"Authorization": f"Bearer {SLACK_TOKEN}", "Content-Type": "application/json"},
        json={
            "canvas_id": canvas_id,
            "changes": [{"operation": "replace", "document_content": {"type": "markdown", "markdown": markdown}}],
        },
        timeout=30,
    )
    result = resp.json()
    if not result.get("ok"):
        print(f"ERROR updating canvas {canvas_id}: {result.get('error')}")
        return False
    print(f"Updated canvas {canvas_id}")
    return True


def main():
    today = date.today()
    if today.weekday() >= 5:
        print("Weekend, skipping.")
        return

    date_str = f"{today.day}.{today.month}.{today.year}"
    menus = load_menus()

    # Czech
    cz_message = build_czech_message(menus, date_str)
    cz_canvas = build_czech_canvas(menus, date_str)
    print("--- Czech message built ---")

    if TEST_MODE:
        print("*** TEST MODE — posting to test channel, skipping canvases ***")

    slack_post_message(CZ_CHANNEL, cz_message)
    if not TEST_MODE:
        slack_update_canvas(CZ_CANVAS, cz_canvas)

    # English (translate via Claude)
    print("--- Translating to English ---")
    en_message = translate_to_english(cz_message)
    # Fix the canvas link for English version
    en_message = en_message.replace(CZ_CANVAS, EN_CANVAS)
    en_canvas = build_english_canvas(en_message)

    slack_post_message(EN_CHANNEL, en_message)
    if not TEST_MODE:
        slack_update_canvas(EN_CANVAS, en_canvas)

    print("Done!")


if __name__ == "__main__":
    main()
