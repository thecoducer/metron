"""
Unit tests for api/physical_gold.py — price enrichment and totals.
"""

import unittest

from app.api.physical_gold import calculate_totals, enrich_holdings_with_prices


class TestEnrichHoldingsWithPrices(unittest.TestCase):
    def test_24k_gold_enrichment(self):
        holdings = [
            {
                "purity": "999 (24K)",
                "weight_gms": 10.0,
                "bought_ibja_rate_per_gm": 5000.0,
            }
        ]
        gold_prices_data = {
            "prices": {"999": {"am": 5500.0, "pm": 5600.0}},
            "date": "2025-01-01",
        }
        result = enrich_holdings_with_prices(holdings, gold_prices_data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["latest_ibja_price_per_gm"], 5600.0)
        # PL = (5600 - 5000) * 10 = 6000
        self.assertAlmostEqual(result[0]["pl"], 6000.0)
        # PL% = 6000 / (5000 * 10) * 100 = 12.0
        self.assertAlmostEqual(result[0]["pl_pct"], 12.0)

    def test_22k_gold(self):
        holdings = [
            {
                "purity": "916 (22K)",
                "weight_gms": 5.0,
                "bought_ibja_rate_per_gm": 4500.0,
            }
        ]
        gold_prices_data = {
            "prices": {"916": {"pm": 4800.0}},
        }
        result = enrich_holdings_with_prices(holdings, gold_prices_data)
        self.assertEqual(result[0]["latest_ibja_price_per_gm"], 4800.0)

    def test_18k_gold(self):
        holdings = [
            {
                "purity": "750 (18K)",
                "weight_gms": 5.0,
                "bought_ibja_rate_per_gm": 3500.0,
            }
        ]
        gold_prices_data = {"prices": {"750": {"pm": 3800.0}}}
        result = enrich_holdings_with_prices(holdings, gold_prices_data)
        self.assertEqual(result[0]["latest_ibja_price_per_gm"], 3800.0)

    def test_no_prices_data(self):
        holdings = [{"purity": "999", "weight_gms": 10.0, "bought_ibja_rate_per_gm": 5000.0}]
        # pyrefly: ignore [bad-argument-type]
        result = enrich_holdings_with_prices(holdings, None)
        self.assertEqual(result[0]["latest_ibja_price_per_gm"], None)
        self.assertEqual(result[0]["pl"], 0)
        self.assertEqual(result[0]["pl_pct"], 0)

    def test_empty_prices(self):
        holdings = [{"purity": "999", "weight_gms": 10.0, "bought_ibja_rate_per_gm": 5000.0}]
        result = enrich_holdings_with_prices(holdings, {"prices": {}})
        self.assertEqual(result[0]["latest_ibja_price_per_gm"], None)

    def test_empty_holdings(self):
        result = enrich_holdings_with_prices([], {"prices": {"999": {"pm": 5000.0}}})
        self.assertEqual(result, [])

    def test_unknown_purity(self):
        holdings = [{"purity": "Unknown", "weight_gms": 10.0, "bought_ibja_rate_per_gm": 5000.0}]
        gold_prices_data = {"prices": {"999": {"pm": 5600.0}}}
        result = enrich_holdings_with_prices(holdings, gold_prices_data)
        self.assertEqual(result[0]["latest_ibja_price_per_gm"], None)

    def test_missing_weight_or_rate(self):
        holdings = [{"purity": "999", "weight_gms": 0, "bought_ibja_rate_per_gm": 5000.0}]
        gold_prices_data = {"prices": {"999": {"pm": 5600.0}}}
        result = enrich_holdings_with_prices(holdings, gold_prices_data)
        self.assertEqual(result[0]["pl"], 0)

    def test_does_not_mutate_original(self):
        original = {"purity": "999", "weight_gms": 10.0, "bought_ibja_rate_per_gm": 5000.0}
        enrich_holdings_with_prices([original], {"prices": {"999": {"pm": 5600.0}}})
        self.assertNotIn("pl", original)

    def test_zero_invested(self):
        """If bought_ibja_rate_per_gm is 0, pl_pct should be 0 (no division by zero)."""
        holdings = [{"purity": "999", "weight_gms": 10.0, "bought_ibja_rate_per_gm": 0}]
        gold_prices_data = {"prices": {"999": {"pm": 5600.0}}}
        result = enrich_holdings_with_prices(holdings, gold_prices_data)
        self.assertEqual(result[0]["pl"], 0)
        self.assertEqual(result[0]["pl_pct"], 0)


class TestCalculateTotals(unittest.TestCase):
    def test_basic(self):
        holdings = [
            {"weight_gms": 10.0, "bought_ibja_rate_per_gm": 5000.0},
            {"weight_gms": 5.0, "bought_ibja_rate_per_gm": 4500.0},
        ]
        result = calculate_totals(holdings)
        self.assertEqual(result["total_weight_gms"], 15.0)
        self.assertEqual(result["total_invested"], 10 * 5000 + 5 * 4500)
        self.assertEqual(result["count"], 2)

    def test_empty_holdings(self):
        result = calculate_totals([])
        self.assertEqual(result["total_weight_gms"], 0)
        self.assertEqual(result["total_invested"], 0)
        self.assertEqual(result["count"], 0)

    def test_missing_fields(self):
        result = calculate_totals([{}, {}])
        self.assertEqual(result["total_weight_gms"], 0)
        self.assertEqual(result["total_invested"], 0)
        self.assertEqual(result["count"], 2)


if __name__ == "__main__":
    unittest.main()
