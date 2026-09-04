import numpy as np
import pandas as pd

from backend.app.pullback_scanner import score_ticker_pullback


def _ohlcv_from_close(closes, base_volume=1_000_000, low_vol_tail=0):
    idx = pd.date_range("2023-01-02", periods=len(closes), freq="B")
    closes = np.asarray(closes, dtype=float)
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) + 0.3
    lows = np.minimum(opens, closes) - 0.3
    volume = np.full(len(closes), float(base_volume))
    if low_vol_tail:
        volume[-low_vol_tail:] *= 0.4  # volume drying up during the pullback
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volume},
        index=idx,
    )


def _uptrend_pullback_scenario():
    """A stock that has rallied for ~a year, then pulled back ~7% on light
    volume into its rising 50-day average -- the textbook "buy the dip"
    setup this scanner is meant to catch."""
    rng = np.random.default_rng(1)
    n_up = 220
    uptrend = 50 + np.linspace(0, 50, n_up) + rng.normal(0, 0.5, n_up)
    pullback = np.linspace(uptrend[-1], uptrend[-1] * 0.93, 12) + rng.normal(0, 0.1, 12)
    closes = np.concatenate([uptrend, pullback])
    df = _ohlcv_from_close(closes, low_vol_tail=12)

    idx = df.index
    pos = len(closes) - 1
    df.loc[idx[pos - 1], ["Open", "High", "Low", "Close"]] = [
        closes[-2] * 0.995, closes[-2] * 1.0, closes[-2] * 0.985, closes[-2] * 0.99,
    ]
    df.loc[idx[pos], ["Open", "High", "Low", "Close"]] = [
        closes[-1] * 0.99, closes[-1] * 1.02, closes[-1] * 0.985, closes[-1] * 1.015,
    ]
    return df


def _downtrend_scenario():
    """Below a declining 200-day average -- not an uptrend at all, should be excluded."""
    rng = np.random.default_rng(2)
    closes = np.linspace(150, 60, 230) + rng.normal(0, 0.4, 230)
    return _ohlcv_from_close(closes)


def _mid_range_uptrend_scenario():
    """A genuine uptrend, but currently near the top of its range -- no pullback yet."""
    rng = np.random.default_rng(3)
    closes = 50 + np.linspace(0, 50, 230) + rng.normal(0, 0.5, 230)
    return _ohlcv_from_close(closes)


def test_uptrend_pullback_scores_higher_than_no_pullback():
    pullback = score_ticker_pullback("PULL", _uptrend_pullback_scenario())
    mid_range = score_ticker_pullback("MID", _mid_range_uptrend_scenario())
    assert pullback is not None
    assert mid_range is not None
    assert pullback.score > mid_range.score


def test_downtrend_is_excluded():
    assert score_ticker_pullback("DOWN", _downtrend_scenario()) is None


def test_pullback_reports_near_rising_ma():
    result = score_ticker_pullback("PULL", _uptrend_pullback_scenario())
    assert result is not None
    assert result.near_ma in {"sma20", "sma50", "sma200"}
    assert result.position_in_range < 50  # sitting in the lower half of its range


def test_score_components_sum_to_score():
    result = score_ticker_pullback("PULL", _uptrend_pullback_scenario())
    assert result is not None
    assert abs(sum(result.components.values()) - result.score) < 0.5


def test_insufficient_data_returns_none():
    short_df = _ohlcv_from_close(np.linspace(100, 110, 100))
    assert score_ticker_pullback("SHORT", short_df) is None


def test_penny_stock_filtered_out():
    rng = np.random.default_rng(4)
    penny_closes = 2 + np.linspace(0, 1.5, 230) + rng.normal(0, 0.02, 230)
    penny = _ohlcv_from_close(penny_closes)
    assert score_ticker_pullback("PENNY", penny) is None
