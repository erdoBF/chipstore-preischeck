#!/usr/bin/env python3
"""Farblogik der Teams-Punkte, ohne Netz und ohne Shop."""
import os
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import preischeck


BERLIN = ZoneInfo("Europe/Berlin")


def gap_row(name, gtin, price, diff, best_total):
    return {
        "name": name,
        "gtin": gtin,
        "sku": "",
        "url": "",
        "price": price,
        "diff": diff,
        "best": {"total": best_total, "merchant": "Shop", "shipping": 0, "delivery": ""},
        "others": [{"merchant": "Shop", "total": best_total}],
        "chip_listed": True,
    }


def win_row(name, gtin, price, next_total):
    return {
        "name": name,
        "gtin": gtin,
        "sku": "",
        "url": "",
        "price": price,
        "diff": round(price - next_total, 2),
        "best": {"total": next_total, "merchant": "Shop", "shipping": 0, "delivery": ""},
        "others": [],
        "chip_listed": True,
    }


def groups(gap, win, tie=None, missing=None, conflict=None):
    return {
        "gap": gap,
        "win": win,
        "tie": tie or [],
        "exclusive": [],
        "missing": missing or [],
        "conflict": conflict or [],
    }


PREV = {
    "date": "2026-11-19",
    "gap": {
        "STAY": {"price": 50.0, "diff": 5.0, "best_total": 45.0},
        "CHG": {"price": 80.0, "diff": 8.0, "best_total": 72.0},
        "LOST": {"price": 100.0, "diff": 10.0, "best_total": 90.0},
        "MISS": {"price": 12.0, "diff": 2.0, "best_total": 10.0},
        "BOTH": {"price": 70.0, "diff": 7.0, "best_total": 63.0},
    },
    "win": {
        "FLIP": {"price": 40.0, "advantage": 5.0, "next_total": 45.0},
        "KEEP": {"price": 30.0, "advantage": 3.0, "next_total": 33.0},
        "TIE": {"price": 10.0, "advantage": 0.0, "next_total": 10.0},
        "BOTH": {"price": 70.0, "advantage": 7.0, "next_total": 77.0},
    },
}


class MarkTests(unittest.TestCase):
    def test_gap_and_win_marks(self):
        lost = gap_row("Flip Rot", "FLIP", 40, 10, 30)
        stay = gap_row("Bleibt Teuer", "STAY", 50, 5, 45)
        changed = gap_row("Abstand Neu", "CHG", 80, 11, 69)
        fresh = gap_row("Ganz Neu", "NEW", 15, 1, 14)
        both = gap_row("Beides", "BOTH", 70, 7, 63)
        self.assertEqual(preischeck.gap_mark(lost, PREV["gap"], PREV["win"]), "dark_red")
        self.assertEqual(preischeck.gap_mark(stay, PREV["gap"], PREV["win"]), "yellow")
        self.assertEqual(preischeck.gap_mark(changed, PREV["gap"], PREV["win"]), "red")
        self.assertEqual(preischeck.gap_mark(fresh, PREV["gap"], PREV["win"]), "red")
        self.assertEqual(preischeck.gap_mark(both, PREV["gap"], PREV["win"]), "dark_red")

        gained = win_row("Wird Guenstig", "LOST", 90, 100)
        kept = win_row("Bleibt Guenstig", "KEEP", 30, 33)
        fresh_win = win_row("Frisch Guenstig", "FRESH", 20, 25)
        self.assertEqual(preischeck.win_mark(gained, PREV["gap"]), "dark_green")
        self.assertEqual(preischeck.win_mark(kept, PREV["gap"]), "green")
        self.assertEqual(preischeck.win_mark(fresh_win, PREV["gap"]), "green")
        self.assertEqual(preischeck.win_mark(gained, {}), "green")

    def test_legend_and_rows(self):
        gap = [
            gap_row("Flip Rot", "FLIP", 40, 10, 30),
            gap_row("Bleibt Teuer", "STAY", 50, 5, 45),
            gap_row("Abstand Neu", "CHG", 80, 11, 69),
            gap_row("Ganz Neu", "NEW", 15, 1, 14),
        ]
        win = [
            win_row("Wird Guenstig", "LOST", 90, 100),
            win_row("Bleibt Guenstig", "KEEP", 30, 33),
            win_row("Frisch Guenstig", "FRESH", 20, 25),
        ]
        tie = [{
            "name": "Gleichauf",
            "gtin": "TIE",
            "sku": "",
            "url": "",
            "price": 10,
            "others": [{"merchant": "Otto", "total": 10}],
        }]
        missing = [{
            "name": "Ohne Seite",
            "gtin": "MISS",
            "sku": "",
            "url": "",
            "price": 12,
            "reason": "Im BestCheck-Frontend nicht gelistet",
        }]
        generated = datetime(2026, 11, 20, 8, 0, tzinfo=BERLIN)
        text = preischeck.render_teams_text(groups(gap, win, tie, missing), generated, PREV)
        m = preischeck.TEAMS_MARK
        self.assertIn(
            f"{m['dark_red']} Bestpreis verloren · {m['red']} neu/geändert · "
            f"{m['yellow']} unverändert · {m['gray']} geteilter Preis · "
            f"{m['dark_green']} Bestpreis gewonnen · {m['green']} Bestpreis · "
            f"{m['black']} nicht gelistet",
            text,
        )
        self.assertIn("Vergleich zum Vortag (19.11.2026).", text)
        for emoji, name in (
            (m["dark_red"], "Flip Rot"),
            (m["yellow"], "Bleibt Teuer"),
            (m["red"], "Abstand Neu"),
            (m["red"], "Ganz Neu"),
            (m["dark_green"], "Wird Guenstig"),
            (m["green"], "Bleibt Guenstig"),
            (m["green"], "Frisch Guenstig"),
            (m["gray"], "Gleichauf"),
            (m["black"], "Ohne Seite"),
        ):
            self.assertIn(f"{emoji} {name}", text)

    def test_first_run_has_no_transition_colors(self):
        generated = datetime(2026, 11, 20, 8, 0, tzinfo=BERLIN)
        text = preischeck.render_teams_text(
            groups([gap_row("Ganz Neu", "NEW", 15, 1, 14)], [win_row("Frisch Guenstig", "FRESH", 20, 25)]),
            generated,
            None,
        )
        m = preischeck.TEAMS_MARK
        self.assertIn("Erster Lauf", text)
        self.assertIn(f"{m['red']} Ganz Neu", text)
        self.assertIn(f"{m['green']} Frisch Guenstig", text)
        self.assertNotIn(f"{m['dark_red']} Ganz Neu", text)
        self.assertNotIn(f"{m['dark_green']} Frisch Guenstig", text)

    def test_conflict_table(self):
        conflict = [
            {
                "name": "Preis Konflikt",
                "gtin": "CONFLICT1",
                "sku": "",
                "url": "",
                "price": 99.0,
                "kind": "price_mismatch",
                "bc": {"id": 1, "url": "https://example.com"},
                "offers": [{"chip": True, "price": 89.0}],
                "chip_offer": {"price": 89.0, "updated": "2026-01-01"},
            },
            {
                "name": "Nicht Auf BC",
                "gtin": "CONFLICT2",
                "sku": "",
                "url": "",
                "price": 12.0,
                "kind": "known",
                "text": "Testhinweis",
                "bc": {"id": 2, "url": "https://example.com"},
                "offers": [{"chip": False, "price": 10.0, "merchant": "Otto"}],
            },
        ]
        generated = datetime(2026, 11, 20, 8, 0, tzinfo=BERLIN)
        text = preischeck.render_teams_text(groups([], [], conflict=conflict), generated, None)
        m = preischeck.TEAMS_MARK
        self.assertIn("## Datensätze prüfen", text)
        self.assertIn("Preis Konflikt", text)
        self.assertIn(f"{m['black']} Nicht Auf BC", text)


if __name__ == "__main__":
    unittest.main()
