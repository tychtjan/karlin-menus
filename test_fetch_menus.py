#!/usr/bin/env python3
"""Tests for menu validity date-range parsing in fetch_menus.py."""

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from fetch_menus import (
    collapse_whitespace,
    discover_sancarlo_indices,
    fetch_pivo,
    fetch_tankovna,
    menu_covers_today,
    parse_pivo_site,
    resolve_menu_start,
    sancarlo_image_name,
    select_sancarlo_index,
    strip_allergens,
    weeks_between,
)


class TestCollapseWhitespace(unittest.TestCase):
    def test_collapses_newlines_and_indentation(self):
        raw = "Kuřecí\n                               kaldoun\n     s\n  nudlemi"
        self.assertEqual(collapse_whitespace(raw), "Kuřecí kaldoun s nudlemi")

    def test_strips_leading_and_trailing_whitespace(self):
        self.assertEqual(collapse_whitespace("  Panna cotta \n"), "Panna cotta")

    def test_plain_text_unchanged(self):
        self.assertEqual(
            collapse_whitespace("Caprese salát se sýrem stracciatella"),
            "Caprese salát se sýrem stracciatella",
        )

    def test_empty_string(self):
        self.assertEqual(collapse_whitespace(""), "")


class TestStripAllergens(unittest.TestCase):
    def test_strips_plain_trailing_codes(self):
        self.assertEqual(
            strip_allergens("Grilovaná vepřová panenka, dračí omáčka, rýže 4, 5, 6, 7, 11, 14"),
            "Grilovaná vepřová panenka, dračí omáčka, rýže",
        )

    def test_strips_codes_with_letter_suffix(self):
        self.assertEqual(strip_allergens("Bílá zelňačka s houbami 1a, 7, 9, 12"), "Bílá zelňačka s houbami")

    def test_strips_single_code(self):
        self.assertEqual(strip_allergens("Salát coleslaw 12"), "Salát coleslaw")

    def test_strips_starred_codes(self):
        self.assertEqual(strip_allergens("Svíčková na smetaně *1a, 7, 9"), "Svíčková na smetaně")

    def test_keeps_name_without_codes(self):
        self.assertEqual(strip_allergens("Pizza con funghi"), "Pizza con funghi")

    def test_keeps_volume_suffix(self):
        self.assertEqual(strip_allergens("Polévka dne 0,33l"), "Polévka dne 0,33l")

    def test_keeps_trailing_numbers_that_are_not_allergen_codes(self):
        for name in ["Hranolky 150g", "Steak 250", "Menu 2026", "Vitamín B12", "Kuře 1/2",
                     "Pivo 0,5", "Polévka 0,33", "Menu 123"]:
            with self.subTest(name=name):
                self.assertEqual(strip_allergens(name), name)

    def test_strips_space_and_semicolon_separated_codes(self):
        self.assertEqual(strip_allergens("Kulajda *1a 7 9"), "Kulajda")
        self.assertEqual(strip_allergens("Řízek 1a; 3; 7"), "Řízek")

    def test_strips_uppercase_sub_codes(self):
        self.assertEqual(strip_allergens("GULÁŠ 1A, 3, 7"), "GULÁŠ")


class TestFetchTankovna(unittest.TestCase):
    def test_strips_stray_whitespace_from_cms_names(self):
        payload = {
            "result": {
                "soup": {"name": "hovězí  vývar\n", "price": 45},
                "dishes": [{"name": "fish and chips s hranolkami\t", "price": 209}],
            }
        }
        resp = MagicMock()
        resp.json.return_value = payload
        with patch("fetch_menus.requests.get", return_value=resp):
            menu = fetch_tankovna()

        self.assertEqual(menu["soup"]["name"], "Hovězí Vývar")
        self.assertEqual(menu["dishes"][0]["name"], "Fish And Chips S Hranolkami")


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


class TestSancarloImageName(unittest.TestCase):
    def test_first_week_has_no_suffix(self):
        self.assertEqual(sancarlo_image_name(0), "menu.png")

    def test_later_weeks_are_numbered(self):
        self.assertEqual(sancarlo_image_name(1), "menu_1.png")
        self.assertEqual(sancarlo_image_name(7), "menu_7.png")
        self.assertEqual(sancarlo_image_name(10), "menu_10.png")


class TestDiscoverSancarloIndices(unittest.TestCase):
    def test_finds_the_whole_uploaded_batch(self):
        present = set(range(11))
        found = discover_sancarlo_indices(lambda i: i in present)
        self.assertEqual(found, list(range(11)))

    def test_tolerates_a_single_gap_in_the_batch(self):
        present = set(range(11)) - {3}
        found = discover_sancarlo_indices(lambda i: i in present)
        self.assertEqual(found, [0, 1, 2, 4, 5, 6, 7, 8, 9, 10])

    def test_stops_after_a_run_of_misses(self):
        probed = []

        def exists(index):
            probed.append(index)
            return index < 2

        self.assertEqual(discover_sancarlo_indices(exists), [0, 1])
        self.assertEqual(probed, [0, 1, 2, 3, 4])

    def test_returns_nothing_when_no_images_are_published(self):
        self.assertEqual(discover_sancarlo_indices(lambda i: False), [])

    def test_respects_the_hard_cap(self):
        found = discover_sancarlo_indices(lambda i: True, max_candidates=5)
        self.assertEqual(found, [0, 1, 2, 3, 4])


class TestResolveMenuStart(unittest.TestCase):
    def test_picks_the_year_closest_to_today(self):
        self.assertEqual(resolve_menu_start("31.08", date(2026, 9, 2)), date(2026, 8, 31))

    def test_rolls_back_into_the_previous_year(self):
        self.assertEqual(resolve_menu_start("29.12", date(2027, 1, 1)), date(2026, 12, 29))

    def test_unparseable_input_returns_none(self):
        self.assertIsNone(resolve_menu_start("June 1st", date(2026, 9, 2)))
        self.assertIsNone(resolve_menu_start(None, date(2026, 9, 2)))
        self.assertIsNone(resolve_menu_start("31.02", date(2026, 9, 2)))


class TestWeeksBetween(unittest.TestCase):
    def test_same_week_is_zero(self):
        self.assertEqual(weeks_between(date(2026, 8, 31), date(2026, 9, 2)), 0)

    def test_counts_whole_weeks_forward(self):
        self.assertEqual(weeks_between(date(2026, 7, 13), date(2026, 9, 2)), 7)

    def test_counts_weeks_backward(self):
        self.assertEqual(weeks_between(date(2026, 9, 2), date(2026, 7, 13)), -7)

    def test_ignores_weekday_within_the_week(self):
        self.assertEqual(weeks_between(date(2026, 7, 13), date(2026, 7, 17)), 0)


def _weekly_batch(first_monday, count):
    """Build {index: (valid_from, valid_to)} for a batch of consecutive weeks."""
    from datetime import timedelta

    batch = {}
    for index in range(count):
        start = first_monday + timedelta(weeks=index)
        end = start + timedelta(days=4)
        batch[index] = (start.strftime("%d.%m"), end.strftime("%d.%m"))
    return batch


class TestSelectSancarloIndex(unittest.TestCase):
    def _reader(self, batch, log):
        def read_range(index):
            log.append(index)
            return batch.get(index)

        return read_range

    def test_finds_the_current_week_beyond_the_old_hardcoded_limit(self):
        # Regression: the real batch published 2026-07-15 runs menu.png..menu_10.png
        # and the week of 2026-09-02 is menu_7.png, which the old fixed
        # menu.png..menu_6.png candidate list could never reach.
        batch = _weekly_batch(date(2026, 7, 13), 11)
        log = []
        index = select_sancarlo_index(self._reader(batch, log), list(range(11)), date(2026, 9, 2))
        self.assertEqual(index, 7)

    def test_jumps_to_the_current_week_without_reading_every_image(self):
        batch = _weekly_batch(date(2026, 7, 13), 11)
        log = []
        select_sancarlo_index(self._reader(batch, log), list(range(11)), date(2026, 9, 2))
        self.assertEqual(log, [0, 7])

    def test_reads_only_the_anchor_when_it_is_the_current_week(self):
        batch = _weekly_batch(date(2026, 7, 13), 11)
        log = []
        index = select_sancarlo_index(self._reader(batch, log), list(range(11)), date(2026, 7, 15))
        self.assertEqual(index, 0)
        self.assertEqual(log, [0])

    def test_falls_back_to_a_scan_when_the_batch_skips_a_week(self):
        batch = _weekly_batch(date(2026, 7, 13), 11)
        # Restaurant skipped a holiday week: everything from index 4 shifts a week later.
        for index in range(4, 11):
            shifted = _weekly_batch(date(2026, 7, 13), 12)[index + 1]
            batch[index] = shifted
        log = []
        index = select_sancarlo_index(self._reader(batch, log), list(range(11)), date(2026, 9, 2))
        self.assertEqual(index, 6)

    def test_scans_when_the_anchor_cannot_be_read(self):
        batch = _weekly_batch(date(2026, 7, 13), 11)
        batch[0] = None
        log = []
        index = select_sancarlo_index(self._reader(batch, log), list(range(11)), date(2026, 9, 2))
        self.assertEqual(index, 7)

    def test_scans_when_the_anchor_has_no_printed_dates(self):
        batch = _weekly_batch(date(2026, 7, 13), 11)
        batch[0] = (None, None)
        log = []
        index = select_sancarlo_index(self._reader(batch, log), list(range(11)), date(2026, 9, 2))
        self.assertEqual(index, 7)

    def test_returns_none_when_no_image_covers_today(self):
        batch = _weekly_batch(date(2026, 7, 13), 11)
        log = []
        index = select_sancarlo_index(self._reader(batch, log), list(range(11)), date(2026, 10, 14))
        self.assertIsNone(index)

    def test_returns_none_for_an_empty_batch(self):
        index = select_sancarlo_index(lambda i: None, [], date(2026, 9, 2))
        self.assertIsNone(index)

    def test_never_reads_the_same_image_twice(self):
        batch = _weekly_batch(date(2026, 7, 13), 11)
        log = []
        select_sancarlo_index(self._reader(batch, log), list(range(11)), date(2026, 10, 14))
        self.assertEqual(sorted(log), sorted(set(log)))


def _pivo_day(heading: str, items: list[tuple[str, str]]) -> str:
    rows = "".join(
        '<div class="nectar_food_menu_item"><div class="inner">'
        f'<div class="item_name"><h4>{name}</h4></div>'
        f'<div class="item_price"><h4>{price}</h4></div></div></div>'
        for name, price in items
    )
    return f'<div class="vc_column-inner"><div class="wpb_wrapper"><h5>{heading}</h5>{rows}</div></div>'


PIVO_SITE_HTML = (
    "<html><body>"
    + _pivo_day("26.ŘÍJEN 2026<br />Pondělí", [
        ("Brokolicový krém s taveným sýrem 1a,7,9", "55,-"),
        ("180g Medailonky z panenky, smetanová omáčka 1a,3,7,9,12", "275,-"),
        ("Dýňový cheesecake 1,3,6,7,8", "59,-"),
    ])
    + _pivo_day("28.ŘÍJEN 2026<br />Středa\xa0 \xa0STÁTNÍ SVÁTEK", [("", ""), ("", "")])
    + _pivo_day("29.ŘÍJNA 2026<br />Čtvrtek", [
        ("Hovězí vývar 1a,9", "55,-"),
        ("Guláš 1a", "205,-"),
    ])
    + _pivo_day("HLAVNÍ JÍDLA", [("Tatarák 3", "395,-")])
    + "</body></html>"
).encode("utf-8")


class TestParsePivoSite(unittest.TestCase):
    def test_reads_only_todays_column_with_prices(self):
        menu = parse_pivo_site(PIVO_SITE_HTML, date(2026, 10, 26))

        self.assertTrue(menu["available"])
        self.assertEqual(menu["date"], "2026-10-26")
        self.assertEqual(menu["soup"], {"name": "Brokolicový krém s taveným sýrem", "price": 55})
        self.assertEqual(menu["dishes"], [
            {"name": "Medailonky z panenky, smetanová omáčka", "price": 275},
            {"name": "Dýňový cheesecake", "price": 59},
        ])

    def test_matches_heading_whatever_the_month_spelling(self):
        menu = parse_pivo_site(PIVO_SITE_HTML, date(2026, 10, 29))

        self.assertEqual(menu["soup"]["name"], "Hovězí vývar")
        self.assertEqual(menu["dishes"], [{"name": "Guláš", "price": 205}])

    def test_empty_holiday_column_is_unavailable(self):
        menu = parse_pivo_site(PIVO_SITE_HTML, date(2026, 10, 28))

        self.assertFalse(menu["available"])
        self.assertEqual(menu["dishes"], [])

    def test_missing_day_is_unavailable(self):
        menu = parse_pivo_site(PIVO_SITE_HTML, date(2026, 10, 27))

        self.assertFalse(menu["available"])

    def test_day_number_must_match_not_just_weekday(self):
        menu = parse_pivo_site(PIVO_SITE_HTML, date(2026, 11, 2))

        self.assertFalse(menu["available"])


class TestFetchPivo(unittest.TestCase):
    MENICKA = {"date": "2026-10-26", "restaurant": "Pivo Karlín", "available": True,
               "soup": None, "dishes": [{"name": "Z meníček", "price": None}]}

    def _site(self, menu):
        return patch("fetch_menus.parse_pivo_site", return_value=menu)

    def test_uses_site_menu_when_complete(self):
        site = parse_pivo_site(PIVO_SITE_HTML, date(2026, 10, 26))
        with patch("fetch_menus.requests.get"), self._site(site), \
                patch("fetch_menus.fetch_menicka") as menicka:
            self.assertEqual(fetch_pivo(), site)
        menicka.assert_not_called()

    def test_falls_back_to_menicka_when_site_request_fails(self):
        with patch("fetch_menus.requests.get", side_effect=ConnectionError("down")), \
                patch("fetch_menus.fetch_menicka", return_value=self.MENICKA):
            self.assertEqual(fetch_pivo(), self.MENICKA)

    def test_falls_back_to_menicka_when_site_has_no_menu_today(self):
        empty = {"available": False, "soup": None, "dishes": []}
        with patch("fetch_menus.requests.get"), self._site(empty), \
                patch("fetch_menus.fetch_menicka", return_value=self.MENICKA):
            self.assertEqual(fetch_pivo(), self.MENICKA)

    def test_falls_back_to_menicka_when_a_site_price_is_missing(self):
        partial = {"available": True, "soup": {"name": "Polévka", "price": 55},
                   "dishes": [{"name": "Guláš", "price": None}]}
        with patch("fetch_menus.requests.get"), self._site(partial), \
                patch("fetch_menus.fetch_menicka", return_value=self.MENICKA):
            self.assertEqual(fetch_pivo(), self.MENICKA)


if __name__ == "__main__":
    unittest.main()
