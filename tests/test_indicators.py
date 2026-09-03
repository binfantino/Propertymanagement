import numpy as np
import pandas as pd

from backend.app.indicators import add_all_indicators, atr, bollinger_bands, macd, rsi


def _dates(n):
    return pd.date_range("2024-01-01", periods=n, freq="B")


def test_rsi_uptrend_approaches_100():
    prices = pd.Series(np.linspace(100, 200, 60))
    result = rsi(prices, window=14)
    assert result.iloc[-1] > 90


def test_rsi_flat_prices_is_neutral():
    prices = pd.Series([100.0] * 30)
    result = rsi(prices, window=14)
    assert result.iloc[-1] == 50


def test_macd_turns_positive_after_uptrend():
    prices = pd.Series(np.concatenate([np.linspace(100, 80, 40), np.linspace(80, 130, 40)]))
    result = macd(prices)
    assert result["hist"].iloc[-1] > result["hist"].iloc[40]


def test_bollinger_bands_widen_with_volatility():
    calm = pd.Series([100.0 + (i % 2) * 0.1 for i in range(40)])
    volatile = pd.Series([100.0 + (i % 2) * 10 for i in range(40)])
    calm_bb = bollinger_bands(calm)
    volatile_bb = bollinger_bands(volatile)
    assert volatile_bb["bb_width"].iloc[-1] > calm_bb["bb_width"].iloc[-1]


def test_atr_reacts_to_range_expansion():
    n = 40
    high = pd.Series([101.0] * n)
    low = pd.Series([99.0] * n)
    close = pd.Series([100.0] * n)
    high.iloc[-5:] = 110
    low.iloc[-5:] = 90
    result = atr(high, low, close, window=14)
    assert result.iloc[-1] > result.iloc[-10]


def test_add_all_indicators_returns_expected_columns():
    n = 220
    idx = _dates(n)
    close = pd.Series(100 + np.cumsum(np.random.default_rng(0).normal(0, 1, n)), index=idx)
    df = pd.DataFrame(
        {
            "Open": close.shift(1).fillna(close.iloc[0]),
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": 1_000_000,
        },
        index=idx,
    )
    out = add_all_indicators(df)
    for col in ["sma20", "sma50", "sma200", "rsi14", "macd", "signal", "hist", "bb_upper", "bb_lower", "atr14", "stoch_k", "obv"]:
        assert col in out.columns
    assert len(out) == n
