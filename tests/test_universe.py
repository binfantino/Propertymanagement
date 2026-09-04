import pytest

from backend.app import universe


@pytest.fixture(autouse=True)
def _clear_universe_cache():
    universe._universe_cache.clear()
    yield
    universe._universe_cache.clear()


def test_get_universe_info_falls_back_on_fetch_failure(monkeypatch):
    def _raise():
        raise ConnectionError("no network in this environment")

    monkeypatch.setattr(universe, "fetch_live_universe", _raise)

    info = universe.get_universe_info()

    assert info["source"] == "fallback_snapshot"
    assert info["tickers"] == universe.DEFAULT_UNIVERSE
    assert info["count"] == len(universe.DEFAULT_UNIVERSE)


def test_get_universe_info_uses_live_data_when_available(monkeypatch):
    monkeypatch.setattr(universe, "fetch_live_universe", lambda: ["AAPL", "MSFT", "ZZZZ"])

    info = universe.get_universe_info()

    assert info["source"] == "live"
    assert info["tickers"] == ["AAPL", "MSFT", "ZZZZ"]
    assert info["count"] == 3


def test_get_universe_info_is_cached(monkeypatch):
    calls = {"n": 0}

    def _fetch():
        calls["n"] += 1
        return ["AAPL"]

    monkeypatch.setattr(universe, "fetch_live_universe", _fetch)

    universe.get_universe_info()
    universe.get_universe_info()
    universe.get_universe_info()

    assert calls["n"] == 1


def test_get_universe_returns_just_the_ticker_list(monkeypatch):
    monkeypatch.setattr(universe, "fetch_live_universe", lambda: ["AAPL", "MSFT"])
    assert universe.get_universe() == ["AAPL", "MSFT"]


def test_default_universe_has_no_duplicates_and_is_sorted():
    assert len(universe.DEFAULT_UNIVERSE) == len(set(universe.DEFAULT_UNIVERSE))
    assert universe.DEFAULT_UNIVERSE == sorted(universe.DEFAULT_UNIVERSE)


def test_default_universe_is_a_substantial_list():
    # Sanity check that the static fallback is a real S&P 500 + Nasdaq-100
    # sized snapshot, not the old small curated list.
    assert len(universe.DEFAULT_UNIVERSE) > 400
