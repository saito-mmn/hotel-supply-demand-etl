import unittest

from hotel_supply_demand.seasonality import seasonal_profile


class SeasonalProfileTest(unittest.TestCase):
    def test_computes_cv_range_and_peak_bottom_month(self) -> None:
        # A synthetic 12-month occupancy series with a clear July peak and
        # February trough.
        monthly = [50.0, 40.0, 55.0, 60.0, 65.0, 70.0, 82.0, 75.0, 68.0, 58.0, 52.0, 47.0]
        profile = seasonal_profile(monthly)
        self.assertAlmostEqual(profile.range_pp, 82.0 - 40.0)
        self.assertEqual(profile.peak_month, 7)
        self.assertEqual(profile.bottom_month, 2)
        self.assertAlmostEqual(profile.average, sum(monthly) / len(monthly))
        self.assertGreater(profile.coefficient_of_variation, 0)

    def test_zero_average_does_not_divide_by_zero(self) -> None:
        profile = seasonal_profile([0.0, 0.0, 0.0])
        self.assertEqual(profile.coefficient_of_variation, 0.0)
        self.assertEqual(profile.range_pp, 0.0)

    def test_requires_at_least_one_value(self) -> None:
        with self.assertRaises(ValueError):
            seasonal_profile([])

    def test_single_value_is_flat(self) -> None:
        profile = seasonal_profile([60.0])
        self.assertEqual(profile.coefficient_of_variation, 0.0)
        self.assertEqual(profile.range_pp, 0.0)
        self.assertEqual(profile.peak_month, 1)
        self.assertEqual(profile.bottom_month, 1)
