#!/usr/bin/env python3
"""Tests for the pre-post formatting failsafe in post_menus.py."""

import os
import unittest

os.environ.setdefault("SLACK_BOT_TOKEN", "test-token")
os.environ.setdefault("CLAUDE_API_KEY", "test-key")

from post_menus import find_format_problem, validate_menus


class TestFindFormatProblem(unittest.TestCase):
    def test_clean_czech_text_passes(self):
        self.assertIsNone(find_format_problem("Kuřecí kaldoun s nudlemi"))
        self.assertIsNone(find_format_problem("Maďarský perkelt se zakysanou smetanou, pečená tarhoňa"))
        self.assertIsNone(find_format_problem("Zuppa di Pomodoro e Basilico — rajčata, bazalka, focaccia"))

    def test_mojibake_detected(self):
        self.assertEqual(find_format_problem("KuĹ™ecĂ­ kaldoun"), "mojibake (encoding corruption)")
        self.assertEqual(find_format_problem("BatĂˇtovĂ˝ krĂ©m"), "mojibake (encoding corruption)")

    def test_double_mangled_mojibake_detected(self):
        self.assertEqual(find_format_problem("Kuĺ™ecă­ vă˝var"), "mojibake (encoding corruption)")

    def test_raw_html_whitespace_detected(self):
        self.assertEqual(
            find_format_problem("Kuřecí\n                    kaldoun\n                    s nudlemi"),
            "raw HTML whitespace",
        )
        self.assertEqual(find_format_problem("Panna  cotta"), "raw HTML whitespace")

    def test_empty_string_passes(self):
        self.assertIsNone(find_format_problem(""))


class TestValidateMenus(unittest.TestCase):
    @staticmethod
    def make_menu(soup_name, dish_names, available=True):
        return {
            "name": "Test Restaurant",
            "data": {
                "available": available,
                "soup": {"name": soup_name, "price": 50} if soup_name else None,
                "dishes": [{"name": n, "price": 100} for n in dish_names],
            },
        }

    def test_clean_menu_stays_available(self):
        menus = validate_menus([self.make_menu("Kmínová s vejcem", ["Kuřecí řízek"])])
        self.assertTrue(menus[0]["data"]["available"])

    def test_mojibake_dish_marks_restaurant_unavailable(self):
        menus = validate_menus([self.make_menu("Kmínová s vejcem", ["IndickĂˇ korma"])])
        self.assertFalse(menus[0]["data"]["available"])

    def test_mojibake_soup_marks_restaurant_unavailable(self):
        menus = validate_menus([self.make_menu("KuĹ™ecĂ­ kaldoun", ["Panna cotta"])])
        self.assertFalse(menus[0]["data"]["available"])

    def test_unavailable_menu_left_alone(self):
        menus = validate_menus([self.make_menu(None, [], available=False)])
        self.assertFalse(menus[0]["data"]["available"])

    def test_only_broken_restaurant_dropped(self):
        menus = validate_menus([
            self.make_menu("Kmínová s vejcem", ["Kuřecí řízek"]),
            self.make_menu("KuĹ™ecĂ­ kaldoun", ["Panna cotta"]),
        ])
        self.assertTrue(menus[0]["data"]["available"])
        self.assertFalse(menus[1]["data"]["available"])


if __name__ == "__main__":
    unittest.main()
