#!/usr/bin/env python3
"""Tests for menu validity date-range parsing in fetch_menus.py."""

import unittest
from datetime import date

from fetch_menus import menu_covers_today


class TestMenuCoversToday(unittest.TestCase):
    def test_today_inside_range(self):
        self.assertTrue(menu_covers_today("01.06", "05.06.", date(2026, 6, 3)))

    def test_today_on_range_boundaries(self):
        self.assertTrue(menu_covers_today("01.06", "05.06", date(2026, 6, 1)))
        self.assertTrue(menu_covers_today("01.06", "05.06", date(2026, 6, 5)))

    def test_past_week_menu_rejected(self):
        self.assertFalse(menu_covers_today("25.05", "29.05.", date(2026, 6, 3)))

    def test_future_week_menu_rejected(self):
        self.assertFalse(menu_covers_today("08.06", "12.06.", date(2026, 6, 3)))
        self.assertFalse(menu_covers_today("15.06.", "19.06.", date(2026, 6, 3)))

    def test_weekend_after_range_rejected(self):
        self.assertFalse(menu_covers_today("01.06", "05.06", date(2026, 6, 6)))

    def test_year_wrap_range_in_january(self):
        self.assertTrue(menu_covers_today("29.12", "02.01", date(2027, 1, 1)))

    def test_year_wrap_range_in_december(self):
        self.assertTrue(menu_covers_today("29.12", "02.01", date(2026, 12, 30)))

    def test_extra_whitespace_and_trailing_dots(self):
        self.assertTrue(menu_covers_today(" 01.06. ", " 05.06. ", date(2026, 6, 3)))

    def test_missing_or_garbage_input_rejected(self):
        self.assertFalse(menu_covers_today(None, "05.06", date(2026, 6, 3)))
        self.assertFalse(menu_covers_today("01.06", None, date(2026, 6, 3)))
        self.assertFalse(menu_covers_today("", "", date(2026, 6, 3)))
        self.assertFalse(menu_covers_today("June 1st", "June 5th", date(2026, 6, 3)))

    def test_invalid_calendar_date_rejected(self):
        self.assertFalse(menu_covers_today("31.02", "05.06", date(2026, 6, 3)))


if __name__ == "__main__":
    unittest.main()
