#!/usr/bin/env python3
"""Alphabetische Produktreihenfolge in den Tabellen."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import preischeck


def item(n, name, price, best=None, listed=True):
    product = {
        "name": name,
        "sku": f"sku-{n}",
        "gtin": f"{n:013d}",
        "price": price,
        "list_price": None,
        "bware": False,
        "url": f"https://shop.example/{n}",
        "offers": [],
        "bc": {"id": "1", "url": "https://bestcheck.example/"} if listed else None,
    }
    if best is not None:
        product["offers"] = [{
            "merchant": "Anderer",
            "chip": False,
            "price": best,
            "shipping": 0.0,
            "total": best,
            "delivery": "",
            "updated": "",
        }]
    return product


class SortTests(unittest.TestCase):
    def test_german_dictionary_order(self):
        names = ["Größe", "CHIP", "Apfel", "Ähre", "grube", "Cosori"]
        ordered = sorted(names, key=preischeck.product_name_key)
        self.assertEqual(ordered, ["Ähre", "Apfel", "CHIP", "Cosori", "Größe", "grube"])

    def test_tables_are_alphabetical_and_top_gaps_stay_by_amount(self):
        products = [
            item(1, "Zulu", 150, 100),
            item(2, "alpha", 11, 10),
            item(3, "Mitte", 70, 30),
            item(4, "Größe", 40, 50),
            item(5, "Ähre", 20, 20),
            item(6, "Ohne Liste", 9, listed=False),
        ]
        groups = preischeck.classify(products)
        self.assertEqual([r["name"] for r in groups["gap"]], ["alpha", "Mitte", "Zulu"])
        self.assertEqual([r["name"] for r in groups["win"]], ["Größe"])
        self.assertEqual([r["name"] for r in groups["tie"]], ["Ähre"])
        self.assertEqual([r["name"] for r in groups["missing"]], ["Ohne Liste"])
        summary = preischeck.report_summary(groups)
        self.assertIn("Zulu", summary["top3"])
        self.assertTrue(summary["top3"].startswith("Zulu"))
        self.assertIn("Mitte", summary["top3"])

    def test_sort_follows_the_displayed_name_without_brand_prefix(self):
        products = [
            item(1, "Samsung Galaxy Z", 150, 100),
            item(2, "Unold Backmeister", 150, 100),
            item(3, "ECOVACS DEEBOT T80", 150, 100),
            item(4, "Amazfit Balance", 150, 100),
            item(5, "TP-Link Tapo C460", 150, 100),
        ]
        groups = preischeck.classify(products)
        self.assertEqual(
            [r["name"] for r in groups["gap"]],
            ["Amazfit Balance", "Unold Backmeister", "ECOVACS DEEBOT T80", "Samsung Galaxy Z", "TP-Link Tapo C460"],
        )

    def test_winbot_and_enzo_come_first(self):
        products = [
            item(1, "Alpha Gerät", 150, 100),
            item(2, "Pizzaofen Enzo", 150, 100),
            item(3, "Zeta WINBOT W3", 150, 100),
            item(4, "Beta Gerät", 150, 100),
            item(5, "winbot mini 2", 150, 100),
            item(6, "Lorenzo Gerät", 150, 100),
            item(7, "Cosori", 40, 50),
            item(8, "Enzo Mini", 40, 50),
            item(9, "Ohne Liste", 9, listed=False),
            item(10, "WINBOT Ersatz", 9, listed=False),
        ]
        groups = preischeck.classify(products)
        self.assertEqual(
            [r["name"] for r in groups["gap"]],
            ["Pizzaofen Enzo", "winbot mini 2", "Zeta WINBOT W3", "Alpha Gerät", "Beta Gerät", "Lorenzo Gerät"],
        )
        self.assertEqual([r["name"] for r in groups["win"]], ["Enzo Mini", "Cosori"])
        self.assertEqual([r["name"] for r in groups["missing"]], ["WINBOT Ersatz", "Ohne Liste"])


if __name__ == "__main__":
    unittest.main()
