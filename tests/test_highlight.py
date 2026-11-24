#!/usr/bin/env python3
"""Fettschrift für Produkte mit WINBOT oder Enzo, ohne Netz."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import preischeck


class HighlightTests(unittest.TestCase):
    def test_matches_whole_word_any_case(self):
        self.assertTrue(preischeck.is_highlight("WINBOT W2 PRO OMNI"))
        self.assertTrue(preischeck.is_highlight("Ecovacs winbot mini 2"))
        self.assertTrue(preischeck.is_highlight("Pizzaofen Enzo"))
        self.assertTrue(preischeck.is_highlight("pizzaofen ENZO 2000"))
        self.assertFalse(preischeck.is_highlight("Lorenzo Kaffeemaschine"))
        self.assertFalse(preischeck.is_highlight("Galaxy Z Flip 8"))

    def test_teams_label_is_bold(self):
        rows = [
            {"name": "WINBOT W2 PRO OMNI", "price": 379.0},
            {"name": "Galaxy Z Flip 8", "price": 1049.0},
        ]
        labels = preischeck.teams_product_labels(rows)
        self.assertEqual(labels[1], "Galaxy Z Flip 8")
        self.assertNotIn("WINBOT", labels[0])
        back = {ord(v): chr(k) for k, v in preischeck._TEAMS_BOLD.items()}
        self.assertEqual(labels[0].translate(back), "WINBOT W2 PRO OMNI")

    def test_html_row_is_bold(self):
        row = {"name": "Pizzaofen Enzo", "url": "https://shop.example/x"}
        cell = preischeck.name_cell(row, row["url"])
        self.assertEqual(cell, '<a href="https://shop.example/x"><b>Pizzaofen Enzo</b></a>')
        plain = preischeck.name_cell({"name": "Galaxy Z Flip 8"})
        self.assertEqual(plain, "Galaxy Z Flip 8")


if __name__ == "__main__":
    unittest.main()
