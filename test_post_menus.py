#!/usr/bin/env python3
"""Tests for the pre-post formatting failsafe in post_menus.py."""

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("SLACK_BOT_TOKEN", "test-token")
os.environ.setdefault("CLAUDE_API_KEY", "test-key")

from menu_format import LABELS
import post_menus
from post_menus import find_format_problem, post_menu, validate_menus


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

    def test_null_dishes_does_not_crash(self):
        menu = self.make_menu("Kmínová s vejcem", [])
        menu["data"]["dishes"] = None
        self.assertTrue(validate_menus([menu])[0]["data"]["available"])

    def test_only_broken_restaurant_dropped(self):
        menus = validate_menus([
            self.make_menu("Kmínová s vejcem", ["Kuřecí řízek"]),
            self.make_menu("KuĹ™ecĂ­ kaldoun", ["Panna cotta"]),
        ])
        self.assertTrue(menus[0]["data"]["available"])
        self.assertFalse(menus[1]["data"]["available"])


def slack_reply(ok, error=None):
    reply = MagicMock()
    reply.json.return_value = {"ok": ok, **({"error": error} if error else {})}
    return reply


class TestPostMenu(unittest.TestCase):
    menus = [{
        "name": "Test",
        "emoji": ":beer:",
        "data": {"available": True, "soup": None, "dishes": [{"name": "Řízek", "price": 199}]},
    }]

    def post(self, *replies):
        with patch("post_menus.requests.post", side_effect=list(replies)) as mock_post:
            ok = post_menu("C1", self.menus, "20.10.2026", LABELS["cs"], "F1")
        return ok, [call.kwargs["json"] for call in mock_post.call_args_list]

    def test_posts_table_blocks_once_on_success(self):
        ok, payloads = self.post(slack_reply(True))
        self.assertTrue(ok)
        self.assertEqual(len(payloads), 1)
        self.assertTrue(any(b["type"] == "table" for b in payloads[0]["blocks"]))
        self.assertTrue(payloads[0]["text"])

    def test_falls_back_to_mrkdwn_when_blocks_rejected(self):
        ok, payloads = self.post(slack_reply(False, "invalid_blocks"), slack_reply(True))
        self.assertTrue(ok)
        self.assertEqual(len(payloads), 2)
        self.assertNotIn("blocks", payloads[1])
        self.assertIn("Řízek", payloads[1]["text"])

    def test_reports_failure_when_fallback_also_fails(self):
        ok, payloads = self.post(slack_reply(False, "invalid_blocks"), slack_reply(False, "channel_not_found"))
        self.assertFalse(ok)
        self.assertEqual(len(payloads), 2)

    def test_no_fallback_after_a_chunk_was_already_posted(self):
        menus = self.menus * 40
        with patch("post_menus.chunk_blocks", side_effect=lambda b: [b[:2], b[2:]]):
            with patch("post_menus.requests.post", side_effect=[slack_reply(True), slack_reply(False, "invalid_blocks")]) as mock_post:
                ok = post_menu("C1", menus, "20.10.2026", LABELS["cs"], "F1")
        self.assertFalse(ok)
        self.assertEqual(mock_post.call_count, 2)


class TestMainExitStatus(unittest.TestCase):
    menus = [{
        "name": "Test",
        "emoji": ":beer:",
        "data": {"available": True, "soup": None, "dishes": [{"name": "Řízek", "price": 199}]},
    }]

    def run_main(self, post_ok, canvas_ok):
        weekday = MagicMock()
        weekday.today.return_value = MagicMock(weekday=lambda: 0, day=20, month=10, year=2026)
        with patch.object(post_menus, "date", weekday), \
                patch.object(post_menus, "TEST_MODE", False), \
                patch.object(post_menus, "load_menus", return_value=self.menus), \
                patch.object(post_menus, "translate_menus", return_value=self.menus), \
                patch.object(post_menus, "post_menu", return_value=post_ok), \
                patch.object(post_menus, "slack_update_canvas", return_value=canvas_ok):
            post_menus.main()

    def test_exits_cleanly_when_everything_posted(self):
        self.run_main(post_ok=True, canvas_ok=True)

    def test_exits_nonzero_when_a_post_failed(self):
        with self.assertRaises(SystemExit) as ctx:
            self.run_main(post_ok=False, canvas_ok=True)
        self.assertEqual(ctx.exception.code, 1)

    def test_exits_nonzero_when_a_canvas_update_failed(self):
        with self.assertRaises(SystemExit) as ctx:
            self.run_main(post_ok=True, canvas_ok=False)
        self.assertEqual(ctx.exception.code, 1)

    def test_english_side_still_runs_after_czech_post_failure(self):
        with patch.object(post_menus, "translate_menus", return_value=self.menus) as translate:
            with self.assertRaises(SystemExit):
                weekday = MagicMock()
                weekday.today.return_value = MagicMock(weekday=lambda: 0, day=20, month=10, year=2026)
                with patch.object(post_menus, "date", weekday), \
                        patch.object(post_menus, "TEST_MODE", False), \
                        patch.object(post_menus, "load_menus", return_value=self.menus), \
                        patch.object(post_menus, "post_menu", return_value=False), \
                        patch.object(post_menus, "slack_update_canvas", return_value=True):
                    post_menus.main()
        translate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
