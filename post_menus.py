#!/usr/bin/env python3
"""Post daily lunch menus to Slack channels and update canvases."""

import json
import os
import sys
from datetime import date

import requests

from menu_format import LABELS, build_canvas, build_message
from menu_translate import TranslationError, translate_menus
from slack_blocks import build_blocks, chunk_blocks

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
    {"file": "sancarlo.json", "emoji": ":pizza:", "name": "San Carlo"},
    {"file": "dvorek.json", "emoji": ":deciduous_tree:", "name": "Dvorek Karlín"},
    {"file": "jidlovice.json", "emoji": ":stew:", "name": "Jídlovice Karlín"},
]

# Characters that show up when UTF-8 Czech is mis-decoded (e.g. as windows-1250)
# but never appear in legitimate menu text
MOJIBAKE_CHARS = set("ĹĺĂăĽľÄ�")


def find_format_problem(text):
    """Return a description of a formatting problem in text, or None if clean."""
    if any(ch in MOJIBAKE_CHARS for ch in text):
        return "mojibake (encoding corruption)"
    if "\n" in text or "\t" in text or "  " in text:
        return "raw HTML whitespace"
    return None


def validate_menus(menus):
    """Failsafe: mark restaurants with corrupted text unavailable instead of posting garbage."""
    for menu in menus:
        data = menu["data"]
        if not data.get("available"):
            continue
        soup = data.get("soup")
        items = ([soup] if soup else []) + (data.get("dishes") or [])
        for item in items:
            problem = find_format_problem(item.get("name") or "")
            if problem:
                sample = (item.get("name") or "")[:60]
                print(f'::warning::{menu["name"]}: {problem} in "{sample}" — marking unavailable')
                data["available"] = False
                break
    return menus


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


def slack_post_message(channel, text, blocks=None):
    """Post a message to a Slack channel; text is the notification fallback when blocks are given."""
    payload = {"channel": channel, "text": text, "unfurl_links": False, "unfurl_media": False}
    if blocks:
        payload["blocks"] = blocks
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {SLACK_TOKEN}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    result = resp.json()
    if not result.get("ok"):
        detail = result.get("errors") or result.get("response_metadata") or ""
        print(f"ERROR posting to {channel}: {result.get('error')} {detail}".rstrip())
        return False
    print(f"Posted to {channel}")
    return True


def post_menu(channel, menus, date_str, labels, canvas_id):
    """Post the menu as table blocks; if Slack rejects the first message, post plain mrkdwn instead."""
    title = f"{labels['title']} — {date_str}"
    chunks = chunk_blocks(build_blocks(menus, date_str, labels, canvas_id))
    for i, chunk in enumerate(chunks):
        if slack_post_message(channel, title, chunk):
            continue
        if i > 0:
            print(f"::error::Only part of the menu was posted to {channel}")
            return False
        print("Table blocks rejected, falling back to mrkdwn")
        return slack_post_message(channel, build_message(menus, date_str, labels, canvas_id))
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
    menus = validate_menus(load_menus())

    # Czech
    cz_canvas = build_canvas(menus, date_str, LABELS["cs"])

    if TEST_MODE:
        print("*** TEST MODE — posting to test channel, skipping canvases ***")

    results = [post_menu(CZ_CHANNEL, menus, date_str, LABELS["cs"], CZ_CANVAS)]
    if not TEST_MODE:
        results.append(slack_update_canvas(CZ_CANVAS, cz_canvas))

    # English (translate names via Claude)
    print("--- Translating to English ---")
    try:
        en_menus = translate_menus(menus, CLAUDE_API_KEY)
    except TranslationError as e:
        print(f"::error::Translator output rejected: {e}")
        sys.exit(1)
    en_canvas = build_canvas(en_menus, date_str, LABELS["en"])

    results.append(post_menu(EN_CHANNEL, en_menus, date_str, LABELS["en"], EN_CANVAS))
    if not TEST_MODE:
        results.append(slack_update_canvas(EN_CANVAS, en_canvas))

    if not all(results):
        print("::error::At least one Slack post or canvas update failed")
        sys.exit(1)

    print("Done!")


if __name__ == "__main__":
    main()
