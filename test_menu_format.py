#!/usr/bin/env python3
"""Tests for menu_format.py."""

import unittest

from menu_format import LABELS, build_message, format_restaurant_canvas


def make_menu(soup=None, dishes=(), available=True, name="Test", emoji=":beer:"):
    return {
        "name": name,
        "emoji": emoji,
        "data": {
            "available": available,
            "soup": {"name": soup, "price": 45} if soup else None,
            "dishes": [{"name": n, "price": p} for n, p in dishes],
        },
    }


class TestFormatRestaurantCanvas(unittest.TestCase):
    def test_renders_soup_and_dishes_as_table_rows(self):
        menu = make_menu("Hovězí vývar", [("Řízek", 199), ("Gulášek", 189)])
        lines = format_restaurant_canvas(menu, LABELS["cs"]).split("\n")
        self.assertEqual(lines[0], "## :beer: Test")
        self.assertEqual(lines[2:], [
            "| # | Jídlo | Cena |",
            "|---|---|---|",
            "| Polévka | Hovězí vývar | 45 Kč |",
            "| 1 | Řízek | 199 Kč |",
            "| 2 | Gulášek | 189 Kč |",
        ])

    def test_menu_without_soup_has_only_dish_rows(self):
        out = format_restaurant_canvas(make_menu(None, [("Řízek", 199)]), LABELS["en"])
        self.assertNotIn("Soup", out)
        self.assertIn("| 1 | Řízek | 199 CZK |", out)

    def test_missing_price_leaves_cell_empty(self):
        out = format_restaurant_canvas(make_menu(None, [("Dezert", None)]), LABELS["cs"])
        self.assertIn("| 1 | Dezert |  |", out)

    def test_pipe_in_name_is_escaped(self):
        out = format_restaurant_canvas(make_menu(None, [("Sýr | šunka", 100)]), LABELS["cs"])
        self.assertIn("| 1 | Sýr \\| šunka | 100 Kč |", out)

    def test_unavailable_restaurant_has_no_table(self):
        out = format_restaurant_canvas(make_menu(available=False), LABELS["en"])
        self.assertIn("No menu available today", out)
        self.assertNotIn("|", out)


class TestBuildMessage(unittest.TestCase):
    def test_english_labels_and_canvas_link(self):
        msg = build_message([make_menu("Soup A", [("Dish", 100)])], "20.10.2026", LABELS["en"], "F123")
        self.assertIn("*Lunch Menus — 20.10.2026*", msg)
        self.assertIn("_Soup:_ Soup A • *45 CZK*", msg)
        self.assertIn("slack.com/docs/T02G0PHRH/F123|Open in canvas", msg)


if __name__ == "__main__":
    unittest.main()
