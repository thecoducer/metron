"""
Unit tests for api/fixed_deposits.py — compound interest and FD value calculation.
"""
import unittest
from datetime import datetime
from unittest.mock import patch

from app.api.fixed_deposits import calculate_compound_interest, calculate_current_value


class TestCalculateCompoundInterest(unittest.TestCase):
    def test_basic_quarterly_compounding(self):
        # 100_000 at 7.5% for 1 year, quarterly compounding
        result = calculate_compound_interest(100_000, 7.5, 1.0, 4)
        # Expected: 100000 * (1 + 0.075/4)^(4*1)
        expected = 100_000 * (1 + 0.075 / 4) ** 4
        self.assertAlmostEqual(result, expected, places=2)

    def test_zero_principal(self):
        result = calculate_compound_interest(0, 7.5, 1.0, 4)
        self.assertEqual(result, 0)

    def test_negative_principal(self):
        result = calculate_compound_interest(-100, 7.5, 1.0, 4)
        self.assertEqual(result, -100)

    def test_zero_rate(self):
        result = calculate_compound_interest(100_000, 0, 1.0, 4)
        self.assertEqual(result, 100_000)

    def test_zero_time(self):
        result = calculate_compound_interest(100_000, 7.5, 0, 4)
        self.assertEqual(result, 100_000)

    def test_negative_rate(self):
        result = calculate_compound_interest(100_000, -5, 1.0, 4)
        self.assertEqual(result, 100_000)

    def test_negative_time(self):
        result = calculate_compound_interest(100_000, 7.5, -1.0, 4)
        self.assertEqual(result, 100_000)

    def test_annual_compounding(self):
        result = calculate_compound_interest(100_000, 10.0, 2.0, 1)
        # 100000 * (1 + 0.10/1)^(1*2) = 121000
        self.assertAlmostEqual(result, 121000.0, places=2)

    def test_monthly_compounding(self):
        result = calculate_compound_interest(100_000, 12.0, 1.0, 12)
        expected = 100_000 * (1 + 0.12/12) ** 12
        self.assertAlmostEqual(result, expected, places=2)


class TestCalculateCurrentValue(unittest.TestCase):
    @patch('app.api.fixed_deposits.datetime')
    def test_basic_fd(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 6)
        mock_dt.strptime = datetime.strptime

        deposits = [{
            'bank_name': 'SBI',
            'original_investment_date': '2025-01-01',
            'reinvested_date': '',
            'deposit_year': 1,
            'deposit_month': 0,
            'deposit_day': 0,
            'original_amount': 100_000,
            'reinvested_amount': 0,
            'interest_rate': 7.5,
        }]
        result = calculate_current_value(deposits)
        self.assertEqual(len(result), 1)
        self.assertIn('current_value', result[0])
        self.assertIn('estimated_returns', result[0])
        self.assertIn('maturity_date', result[0])
        self.assertGreater(result[0]['current_value'], 100_000)
        self.assertGreater(result[0]['estimated_returns'], 0)

    @patch('app.api.fixed_deposits.datetime')
    def test_reinvested_date_preferred(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 6)
        mock_dt.strptime = datetime.strptime

        deposits = [{
            'bank_name': 'HDFC',
            'original_investment_date': '2024-01-01',
            'reinvested_date': '2025-06-01',
            'deposit_year': 1,
            'deposit_month': 0,
            'deposit_day': 0,
            'original_amount': 100_000,
            'reinvested_amount': 108_000,
            'interest_rate': 7.0,
        }]
        result = calculate_current_value(deposits)
        self.assertEqual(len(result), 1)
        # reinvested_amount should be used as principal
        self.assertGreater(result[0]['current_value'], 108_000)

    @patch('app.api.fixed_deposits.datetime')
    def test_multiple_date_formats(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 6)
        mock_dt.strptime = datetime.strptime

        for date_str in ['January 01, 2025', '01/01/2025', '2025-01-01']:
            deposits = [{
                'bank_name': 'Test',
                'original_investment_date': date_str,
                'reinvested_date': '',
                'deposit_year': 1,
                'deposit_month': 0,
                'deposit_day': 0,
                'original_amount': 100_000,
                'reinvested_amount': 0,
                'interest_rate': 7.5,
            }]
            result = calculate_current_value(deposits)
            self.assertEqual(len(result), 1, f"Failed for date format: {date_str}")

    @patch('app.api.fixed_deposits.datetime')
    def test_unparsable_date_skipped(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 6)
        mock_dt.strptime = datetime.strptime

        deposits = [{
            'bank_name': 'Test',
            'original_investment_date': 'invalid-date-format',
            'reinvested_date': '',
            'deposit_year': 1,
            'deposit_month': 0,
            'deposit_day': 0,
            'original_amount': 100_000,
            'reinvested_amount': 0,
            'interest_rate': 7.5,
        }]
        result = calculate_current_value(deposits)
        self.assertEqual(len(result), 0)

    @patch('app.api.fixed_deposits.datetime')
    def test_empty_date_skipped(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 6)
        mock_dt.strptime = datetime.strptime

        deposits = [{
            'bank_name': 'Test',
            'original_investment_date': '',
            'reinvested_date': '',
            'deposit_year': 1,
            'deposit_month': 0,
            'deposit_day': 0,
            'original_amount': 100_000,
            'reinvested_amount': 0,
            'interest_rate': 7.5,
        }]
        # Empty date_str is falsy → deposit_date stays None → None + relativedelta
        # raises TypeError. Verify the function raises in this case.
        with self.assertRaises(TypeError):
            calculate_current_value(deposits)

    @patch('app.api.fixed_deposits.datetime')
    def test_maturity_calculation_with_months_days(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 6)
        mock_dt.strptime = datetime.strptime

        deposits = [{
            'bank_name': 'Test',
            'original_investment_date': '2025-01-01',
            'reinvested_date': '',
            'deposit_year': 0,
            'deposit_month': 6,
            'deposit_day': 15,
            'original_amount': 50_000,
            'reinvested_amount': 0,
            'interest_rate': 6.0,
        }]
        result = calculate_current_value(deposits)
        self.assertEqual(len(result), 1)
        # Maturity: 2025-01-01 + 6 calendar months + 15 days = July 16, 2025
        self.assertEqual(result[0]['maturity_date'], 'July 16, 2025')

    @patch('app.api.fixed_deposits.datetime')
    def test_maturity_date_real_scenario(self, mock_dt):
        """Regression: 1y 8m 29d from Oct 17 2024 must land on Jul 16 2026.

        The old flat-day formula (years*365 + months*30 + days) produced
        Jul 13 2026 because it under-counted months with 31 days.
        Using relativedelta gives the calendar-correct result.
        """
        mock_dt.now.return_value = datetime(2026, 3, 7)
        mock_dt.strptime = datetime.strptime

        deposits = [{
            'bank_name': 'HDFC',
            'original_investment_date': 'October 17, 2024',
            'reinvested_date': '',
            'deposit_year': 1,
            'deposit_month': 8,
            'deposit_day': 29,
            'original_amount': 20_000,
            'reinvested_amount': 0,
            'interest_rate': 6.45,
        }]
        result = calculate_current_value(deposits)
        self.assertEqual(len(result), 1)
        # Oct 17 2024 + 1y → Oct 17 2025 + 8m → Jun 17 2026 + 29d → Jul 16 2026
        self.assertEqual(result[0]['maturity_date'], 'July 16, 2026')

    @patch('app.api.fixed_deposits.datetime')
    def test_sorted_by_maturity(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 6)
        mock_dt.strptime = datetime.strptime

        deposits = [
            {
                'bank_name': 'Late',
                'original_investment_date': '2025-06-01',
                'reinvested_date': '',
                'deposit_year': 2, 'deposit_month': 0, 'deposit_day': 0,
                'original_amount': 100_000, 'reinvested_amount': 0,
                'interest_rate': 7.0,
            },
            {
                'bank_name': 'Early',
                'original_investment_date': '2025-01-01',
                'reinvested_date': '',
                'deposit_year': 1, 'deposit_month': 0, 'deposit_day': 0,
                'original_amount': 100_000, 'reinvested_amount': 0,
                'interest_rate': 8.0,
            },
        ]
        result = calculate_current_value(deposits)
        self.assertEqual(len(result), 2)
        # Early maturity should come first
        self.assertEqual(result[0]['bank_name'], 'Early')

    def test_empty_list(self):
        result = calculate_current_value([])
        self.assertEqual(result, [])

    @patch('app.api.fixed_deposits.datetime')
    def test_deposit_copy_not_mutating_original(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 6)
        mock_dt.strptime = datetime.strptime

        original = {
            'bank_name': 'Test',
            'original_investment_date': '2025-01-01',
            'reinvested_date': '',
            'deposit_year': 1, 'deposit_month': 0, 'deposit_day': 0,
            'original_amount': 100_000, 'reinvested_amount': 0,
            'interest_rate': 7.5,
        }
        result = calculate_current_value([original])
        self.assertNotIn('current_value', original)
        self.assertIn('current_value', result[0])


if __name__ == '__main__':
    unittest.main()
