from dataclasses import replace
import unittest

from coinbase_spot.models import Candle, D
from coinbase_spot.strategy import decide


def bars(rows):
    return tuple(Candle("SOL-USD", i * 60, 60, *map(D, row), D("100"))
                 for i, row in enumerate(rows))


BASE = [("100", "101", "99", "100")] * 3


class StrategyTests(unittest.TestCase):
    def decision(self, candles, in_position=False, timestamp=240):
        return decide(candles, decision_time=timestamp, in_position=in_position,
                      lookback=3, atr_period=2)

    def test_entry_uses_previous_channel_excluding_signal_bar(self):
        candles = bars(BASE + [("100", "104", "99", "103")])
        result = self.decision(candles)
        self.assertEqual(result.action, "ENTER")
        self.assertEqual(result.atr, D("3.5"))
        self.assertEqual(result.decision_time, 240)

    def test_future_perturbation_does_not_change_decision(self):
        candles = bars(BASE + [("100", "104", "99", "103"), ("103", "105", "100", "104")])
        changed = candles[:-1] + (replace(candles[-1], high=D("99999"), low=D("1"), close=D("2")),)
        self.assertEqual(self.decision(candles), self.decision(changed))
        self.assertEqual(self.decision(candles), self.decision(candles[:-1]))

    def test_incomplete_signal_bar_is_not_used(self):
        candles = bars(BASE + [("100", "104", "99", "103")])
        self.assertEqual(self.decision(candles, timestamp=239).action, "HOLD")
        self.assertEqual(self.decision(candles, timestamp=239).reason, "warmup")

    def test_exit_is_sell_to_flat_never_short_entry(self):
        candles = bars(BASE + [("100", "101", "97", "98")])
        self.assertEqual(self.decision(candles, in_position=True).action, "EXIT")
        self.assertEqual(self.decision(candles, in_position=False).action, "HOLD")

    def test_long_position_does_not_add_on_a_breakout(self):
        candles = bars(BASE + [("100", "104", "99", "103")])
        self.assertEqual(self.decision(candles, in_position=True).action, "HOLD")

    def test_parameters_require_positive_integers(self):
        for lookback in (0, -1, True, 3.0):
            with self.subTest(lookback=lookback), self.assertRaises(ValueError):
                decide((), decision_time=0, in_position=False, lookback=lookback)


if __name__ == "__main__":
    unittest.main()
