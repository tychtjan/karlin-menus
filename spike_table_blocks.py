"""Spike: which Slack `table` block shapes does chat.postMessage accept? Posts to the test channel only."""
import os
import sys

import requests

TEST_CHANNEL = "C0AG0MU6HD2"  # copied from post_menus.py (importing it needs CLAUDE_API_KEY)
COLUMN_SETTINGS = [{"align": "left"}, {"is_wrapped": True}, {"align": "right"}]


def cell(text):
    return {"type": "raw_text", "text": text}


def table(rows):
    return {
        "type": "table",
        "rows": [[cell(c) for c in row] for row in rows],
        "column_settings": COLUMN_SETTINGS,
    }


def small_table(label):
    return table([["Dish", "Note", "Price"], [f"{label} soup", "vegetarian", "45"], [f"{label} stew", "gluten", "129"]])


def big_table(chars):
    # 3 columns x 2 data rows + header; spread `chars` of text over the 6 data cells
    chunk = "x" * (chars // 6)
    return table([["Dish", "Note", "Price"], [chunk, chunk, chunk], [chunk, chunk, chunk]])


CASES = {
    "a": [small_table("A1"), {"type": "section", "text": {"type": "mrkdwn", "text": "second table below"}}, small_table("A2")],
    "b": [big_table(9500)],
    "c": [big_table(10500)],
    "e": [table([["Dish", "Note", "Price"], ["Dessert", "", ""]])],
    "d": [table([["Dish", "Note", "Price"], ["Very long dish name " * 12 + "end", "wrapped column", "99"]])],
}


def post(letter, blocks, token):
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"channel": TEST_CHANNEL, "text": f"[spike] case {letter}", "blocks": blocks},
        timeout=30,
    )
    body = resp.json()
    print(f"case {letter}: raw ok={body.get('ok')} error={body.get('error')} errors={body.get('errors')}")
    return "ok" if body.get("ok") else f"error: {body.get('error')}"


def main():
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        sys.exit("SLACK_BOT_TOKEN is not set; export it and rerun.")
    results = {letter: post(letter, blocks, token) for letter, blocks in CASES.items()}
    print("\nSummary\ncase | result\n-----|-------")
    for letter, result in results.items():
        print(f"  {letter}  | {result}")
    print(f"\nReminder: ran against test channel {TEST_CHANNEL}; delete the [spike] messages by hand.")
    print("Case d needs a visual check on desktop and mobile; case e tests empty cells.")


if __name__ == "__main__":
    main()
