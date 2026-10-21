#!/usr/bin/env python3
"""Tests for the Slack Block Kit builders in slack_blocks.py."""

import copy
import glob
import json
import os
import unittest

from slack_blocks import build_blocks, chunk_blocks, table_chars

LABELS_CS = {
    "title": "Obědová menu",
    "soup": "Polévka",
    "currency": "Kč",
    "unavailable": "Menu dnes není k dispozici",
    "canvas_link": "Otevřít v canvasu",
    "dish": "Jídlo",
    "price": "Cena",
}
LABELS_EN = {
    "title": "Lunch Menus",
    "soup": "Soup",
    "currency": "CZK",
    "unavailable": "No menu available today",
    "canvas_link": "Open in canvas",
    "dish": "Dish",
    "price": "Price",
}
CANVAS_ID = "F123ABC"
DATE = "13. 4. 2026"
MENUS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "menus")


def make_menu(name="Pivo", soup=True, dishes=2, price=100, dish_len=10):
    return {
        "name": name,
        "emoji": ":beer:",
        "data": {
            "available": True,
            "soup": {"name": f"{name} soup", "price": 40} if soup else None,
            "dishes": [
                {"name": ("word " * dish_len).strip() + f" {i}", "price": price}
                for i in range(1, dishes + 1)
            ],
        },
    }


def unavailable_menu(name="Closed"):
    return {
        "name": name,
        "emoji": ":x:",
        "data": {"available": False, "soup": None, "dishes": []},
    }


def texts(row):
    return [cell["text"] for cell in row]


def table_of(blocks):
    return [b for b in blocks if b["type"] == "table"]


def restaurant_groups(chunk):
    """(section text, table rows or None) per restaurant section in a chunk."""
    result = []
    for i, block in enumerate(chunk):
        if block["type"] != "section" or "*" not in block["text"]["text"]:
            continue
        if ":knife_fork_plate:" in block["text"]["text"]:
            continue
        nxt = chunk[i + 1] if i + 1 < len(chunk) else None
        rows = nxt["rows"] if nxt and nxt["type"] == "table" else None
        result.append((block["text"]["text"], rows))
    return result


class TestBuildBlocksPerRestaurant(unittest.TestCase):

    def test_available_menu_structure(self):
        menus = [make_menu("Pivo", dishes=2)]

        blocks = build_blocks(menus, DATE, LABELS_CS, CANVAS_ID)

        self.assertEqual([b["type"] for b in blocks], ["section", "section", "table", "section"])
        self.assertEqual(blocks[0]["text"]["type"], "mrkdwn")
        self.assertIn(LABELS_CS["title"], blocks[0]["text"]["text"])
        self.assertIn(DATE, blocks[0]["text"]["text"])
        self.assertEqual(blocks[1]["text"], {"type": "mrkdwn", "text": ":beer: *Pivo*"})
        table = blocks[2]
        self.assertEqual(
            table["column_settings"],
            [{"align": "left"}, {"is_wrapped": True}, {"align": "right"}],
        )
        self.assertTrue(all(c["type"] == "raw_text" for r in table["rows"] for c in r))
        self.assertEqual(texts(table["rows"][0]), ["#", LABELS_CS["dish"], LABELS_CS["price"]])
        self.assertEqual(texts(table["rows"][1]), [LABELS_CS["soup"], "Pivo soup", "40 Kč"])
        self.assertEqual([r[0]["text"] for r in table["rows"][2:]], ["1", "2"])
        self.assertEqual(texts(table["rows"][2])[2], "100 Kč")

    def test_footer_links_to_canvas(self):
        blocks = build_blocks([make_menu()], DATE, LABELS_EN, CANVAS_ID)

        self.assertEqual(
            blocks[-1]["text"]["text"],
            f"<https://gooddata.slack.com/docs/T02G0PHRH/{CANVAS_ID}|{LABELS_EN['canvas_link']}>",
        )

    def test_unavailable_menu_has_section_and_no_table(self):
        blocks = build_blocks([unavailable_menu("Closed")], DATE, LABELS_EN, CANVAS_ID)

        self.assertEqual(table_of(blocks), [])
        self.assertEqual(
            blocks[1]["text"]["text"], f":x: *Closed*\n{LABELS_EN['unavailable']}"
        )

    def test_menu_without_soup_has_no_soup_row(self):
        blocks = build_blocks([make_menu(soup=False, dishes=2)], DATE, LABELS_CS, CANVAS_ID)

        rows = table_of(blocks)[0]["rows"]
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][0]["text"], "1")

    def test_missing_price_gets_placeholder_because_slack_rejects_empty_cells(self):
        menu = make_menu(dishes=1)
        menu["data"]["dishes"][0]["price"] = None
        menu["data"]["soup"]["price"] = 0

        rows = table_of(build_blocks([menu], DATE, LABELS_CS, CANVAS_ID))[0]["rows"]

        self.assertEqual(rows[1][2]["text"], "–")
        self.assertEqual(rows[2][2]["text"], "–")

    def test_en_labels_use_en_currency_and_headers(self):
        rows = table_of(build_blocks([make_menu()], DATE, LABELS_EN, CANVAS_ID))[0]["rows"]

        self.assertEqual(texts(rows[0]), ["#", "Dish", "Price"])
        self.assertEqual(rows[1][0]["text"], "Soup")
        self.assertTrue(rows[1][2]["text"].endswith(" CZK"))

    def test_one_table_per_available_restaurant(self):
        menus = [make_menu("A"), unavailable_menu("B"), make_menu("C")]

        blocks = build_blocks(menus, DATE, LABELS_CS, CANVAS_ID)

        self.assertEqual(len(table_of(blocks)), 2)
        self.assertEqual(len(blocks), 7)

    def test_empty_menu_list_still_has_title_and_footer(self):
        blocks = build_blocks([], DATE, LABELS_CS, CANVAS_ID)

        self.assertEqual(len(blocks), 2)


class TestTableChars(unittest.TestCase):

    def test_counts_all_cell_text(self):
        blocks = build_blocks([make_menu(dishes=1)], DATE, LABELS_EN, CANVAS_ID)

        expected = sum(len(c["text"]) for r in table_of(blocks)[0]["rows"] for c in r)
        self.assertEqual(table_chars(blocks), expected)
        self.assertGreater(expected, 0)

    def test_zero_without_tables(self):
        self.assertEqual(table_chars(build_blocks([], DATE, LABELS_EN, CANVAS_ID)), 0)


class TestChunkBlocks(unittest.TestCase):

    def over_limit_blocks(self, count=10, **kwargs):
        menus = [make_menu(f"R{i}", dishes=8, dish_len=25) for i in range(count)]
        return menus, build_blocks(menus, DATE, LABELS_CS, CANVAS_ID, **kwargs)

    def test_small_input_is_one_chunk_equal_to_input(self):
        blocks = build_blocks([make_menu()], DATE, LABELS_CS, CANVAS_ID)

        self.assertEqual(chunk_blocks(blocks), [blocks])

    def test_over_limit_splits_within_char_budget(self):
        _, blocks = self.over_limit_blocks()
        self.assertGreater(table_chars(blocks), 9000)

        chunks = chunk_blocks(blocks, max_table_chars=9000)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(table_chars(chunk), 9000)

    def test_restaurants_stay_whole_and_in_order(self):
        menus, blocks = self.over_limit_blocks()
        original = {t[0]: t[1] for t in restaurant_groups(blocks)}

        chunks = chunk_blocks(blocks, max_table_chars=9000)

        seen = [g for chunk in chunks for g in restaurant_groups(chunk)]
        self.assertEqual([g[0] for g in seen], [f":beer: *R{i}*" for i in range(len(menus))])
        for text, rows in seen:
            self.assertEqual(rows, original[text])

    def test_title_only_first_and_footer_only_last(self):
        _, blocks = self.over_limit_blocks()

        chunks = chunk_blocks(blocks, max_table_chars=9000)

        flat = [b for chunk in chunks for b in chunk]
        self.assertEqual(flat.count(blocks[0]), 1)
        self.assertEqual(flat.count(blocks[-1]), 1)
        self.assertEqual(chunks[0][0], blocks[0])
        self.assertEqual(chunks[-1][-1], blocks[-1])

    def test_max_blocks_respected(self):
        _, blocks = self.over_limit_blocks(count=10)

        chunks = chunk_blocks(blocks, max_table_chars=10**6, max_blocks=8)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 8)
        self.assertEqual(sum(len(c) for c in chunks), len(blocks))

    def test_max_rows_respected(self):
        _, blocks = self.over_limit_blocks(count=6)

        chunks = chunk_blocks(blocks, max_table_chars=10**6, max_rows=20)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(sum(len(t["rows"]) for t in table_of(chunk)), 20)

    def test_unavailable_restaurant_survives_chunking(self):
        menus = [make_menu(f"R{i}", dishes=8, dish_len=25) for i in range(6)]
        menus.insert(3, unavailable_menu("Closed"))
        blocks = build_blocks(menus, DATE, LABELS_CS, CANVAS_ID)

        chunks = chunk_blocks(blocks, max_table_chars=3000)

        names = [g[0] for c in chunks for g in restaurant_groups(c)]
        self.assertEqual(len(names), 7)
        self.assertTrue(any(n.startswith(":x: *Closed*") for n in names))

    def test_oversized_restaurant_is_truncated_not_dropped(self):
        menu = make_menu("Big", dishes=10, dish_len=60)
        blocks = build_blocks([menu], DATE, LABELS_CS, CANVAS_ID)
        original_rows = table_of(blocks)[0]["rows"]
        budget = 1200
        self.assertGreater(table_chars(blocks), budget)

        chunks = chunk_blocks(blocks, max_table_chars=budget)

        self.assertEqual(len(chunks), 1)
        self.assertLessEqual(table_chars(chunks[0]), budget)
        rows = table_of(chunks[0])[0]["rows"]
        self.assertEqual(len(rows), len(original_rows))
        for new, old in zip(rows[2:], original_rows[2:]):
            self.assertEqual(new[0], old[0])
            self.assertEqual(new[2], old[2])
            self.assertTrue(new[1]["text"].endswith("…"))
            self.assertTrue(old[1]["text"].startswith(new[1]["text"][:-1]))
            self.assertNotIn(" ", new[1]["text"][-2:])

    def test_truncation_cuts_at_word_boundary(self):
        menu = make_menu("Big", soup=False, dishes=1)
        menu["data"]["dishes"][0]["name"] = "alpha beta gamma delta epsilon zeta"
        blocks = build_blocks([menu], DATE, LABELS_CS, CANVAS_ID)
        budget = table_chars(blocks) - 12

        chunks = chunk_blocks(blocks, max_table_chars=budget)

        cell = table_of(chunks[0])[0]["rows"][1][1]["text"]
        self.assertTrue(cell.endswith("…"))
        self.assertIn(cell[:-1], ["alpha", "alpha beta", "alpha beta gamma", "alpha beta gamma delta", "alpha beta gamma delta epsilon"])

    def test_does_not_mutate_input(self):
        _, blocks = self.over_limit_blocks(count=4)
        snapshot = copy.deepcopy(blocks)

        chunk_blocks(blocks, max_table_chars=1500)

        self.assertEqual(blocks, snapshot)


class TestBuildBlocksDoesNotMutate(unittest.TestCase):

    def test_menus_and_labels_unchanged(self):
        menus = [make_menu("A"), unavailable_menu("B")]
        labels = dict(LABELS_CS)
        menus_snapshot = copy.deepcopy(menus)

        build_blocks(menus, DATE, labels, CANVAS_ID)

        self.assertEqual(menus, menus_snapshot)
        self.assertEqual(labels, LABELS_CS)

    def test_repeated_builds_are_independent(self):
        menus = [make_menu("A")]

        first = build_blocks(menus, DATE, LABELS_CS, CANVAS_ID)
        first[1]["text"]["text"] = "changed"
        second = build_blocks(menus, DATE, LABELS_CS, CANVAS_ID)

        self.assertEqual(second[1]["text"]["text"], ":beer: *A*")


class TestSavedMenus(unittest.TestCase):

    def load_menus(self):
        menus = []
        for path in sorted(glob.glob(os.path.join(MENUS_DIR, "*.json"))):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            menus.append({"name": data["restaurant"], "emoji": ":fork_and_knife:", "data": data})
        return menus

    def test_all_saved_menus_fit_after_chunking(self):
        menus = self.load_menus()
        self.assertEqual(len(menus), 6)

        for labels in (LABELS_CS, LABELS_EN):
            blocks = build_blocks(menus, DATE, labels, CANVAS_ID)
            chunks = chunk_blocks(blocks)

            for chunk in chunks:
                self.assertLessEqual(table_chars(chunk), 9000)
                self.assertLessEqual(len(chunk), 50)
            names = [g[0] for c in chunks for g in restaurant_groups(c)]
            self.assertEqual(len(names), 6)

    def test_no_table_cell_is_empty(self):
        menus = self.load_menus()
        menus[0]["data"]["dishes"][0]["price"] = None

        for table in table_of(build_blocks(menus, DATE, LABELS_CS, CANVAS_ID)):
            for row in table["rows"]:
                for cell in row:
                    self.assertTrue(cell["text"], "Slack rejects empty raw_text cells")


if __name__ == "__main__":
    unittest.main()
