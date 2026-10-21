#!/usr/bin/env python3
"""Tests for menu_translate.py."""

import json
import unittest
from unittest.mock import MagicMock, patch

from menu_translate import TranslationError, translate_menus


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


class TestTranslateMenus(unittest.TestCase):
    def run_translate(self, menus, reply):
        client = MagicMock()
        client.messages.create.return_value.content = [MagicMock(text=reply)]
        with patch("menu_translate.anthropic.Anthropic", return_value=client):
            out = translate_menus(menus, "test-key")
        self.sent_to_model = client.messages.create.call_args.kwargs["messages"][0]["content"]
        return out

    def setUp(self):
        self.menus = [
            make_menu("Hovězí vývar", [("Řízek", 199), ("Gulášek", 189)]),
            make_menu(available=False, name="Closed"),
        ]

    def reply(self, soup="Beef broth", dishes=("Schnitzel", "Goulash")):
        return json.dumps([{"soup": soup, "dishes": list(dishes)}, {"soup": None, "dishes": []}])

    def test_translates_names_and_keeps_prices_and_availability(self):
        out = self.run_translate(self.menus, self.reply())
        self.assertEqual(out[0]["data"]["soup"], {"name": "Beef broth", "price": 45})
        self.assertEqual(
            out[0]["data"]["dishes"],
            [{"name": "Schnitzel", "price": 199}, {"name": "Goulash", "price": 189}],
        )
        self.assertFalse(out[1]["data"]["available"])

    def test_does_not_mutate_input(self):
        self.run_translate(self.menus, self.reply())
        self.assertEqual(self.menus[0]["data"]["soup"]["name"], "Hovězí vývar")

    def test_accepts_reply_wrapped_in_code_fence(self):
        out = self.run_translate(self.menus, "```json\n" + self.reply() + "\n```")
        self.assertEqual(out[0]["data"]["soup"]["name"], "Beef broth")

    def test_rejects_wrong_dish_count(self):
        with self.assertRaises(TranslationError):
            self.run_translate(self.menus, self.reply(dishes=("Schnitzel",)))

    def test_rejects_non_string_or_empty_name(self):
        with self.assertRaises(TranslationError):
            self.run_translate(self.menus, self.reply(dishes=("Schnitzel", 5)))
        with self.assertRaises(TranslationError):
            self.run_translate(self.menus, self.reply(dishes=("Schnitzel", " ")))

    def test_rejects_missing_soup(self):
        with self.assertRaises(TranslationError):
            self.run_translate(self.menus, self.reply(soup=None))

    def test_rejects_non_json_and_validation_failed(self):
        with self.assertRaises(TranslationError):
            self.run_translate(self.menus, "Sure! Here is the menu")
        with self.assertRaises(TranslationError):
            self.run_translate(self.menus, "VALIDATION_FAILED: mojibake")

    def test_unavailable_restaurant_text_is_not_sent_to_the_model(self):
        menus = [
            make_menu("Hovězí vývar", [("Řízek", 199)]),
            make_menu("Zzsoup vývar", [("Zzdish řízek", 99)], available=False, name="Broken"),
        ]
        reply = json.dumps([{"soup": "Beef broth", "dishes": ["Schnitzel"]}, {"soup": None, "dishes": []}])
        out = self.run_translate(menus, reply)
        self.assertNotIn("Zzsoup", self.sent_to_model)
        self.assertNotIn("Zzdish", self.sent_to_model)
        self.assertEqual(out[1], menus[1])

    def test_null_dishes_on_unavailable_menu_is_tolerated(self):
        menus = [make_menu(available=False)]
        menus[0]["data"]["dishes"] = None
        out = self.run_translate(menus, json.dumps([{"soup": None, "dishes": []}]))
        self.assertFalse(out[0]["data"]["available"])

    def test_collapses_whitespace_inside_translated_names(self):
        out = self.run_translate(self.menus, self.reply(dishes=("Pork\n  cutlet", "Goulash ")))
        self.assertEqual([d["name"] for d in out[0]["data"]["dishes"]], ["Pork cutlet", "Goulash"])

    def test_rejects_wrong_restaurant_count(self):
        with self.assertRaises(TranslationError):
            self.run_translate(self.menus, json.dumps([{"soup": None, "dishes": []}]))


if __name__ == "__main__":
    unittest.main()
