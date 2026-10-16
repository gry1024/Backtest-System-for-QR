import gc
import weakref

import numpy as np
import pandas as pd
import pytest

from quantbt.data import MarketData


@pytest.fixture
def feather_directory(tmp_path):
    dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2021-01-04", "2026-09-30", "2026-10-16"])
    for name in ("open", "high", "low", "close", "amt", "cumadj"):
        values = np.ones((5, 3)) if name == "cumadj" else np.arange(1, 16).reshape(5, 3).astype(float)
        frame = pd.DataFrame(values, columns=["000001.SZ", "600001.SH", "300001.SZ"])
        frame.insert(0, "date", dates)
        frame.to_feather(tmp_path / (name + ".feather"))
    return tmp_path


def test_end_cutoff_and_future_rows_cannot_affect_adjustment(feather_directory):
    data = MarketData(feather_directory)
    before = data.feature("close").copy()
    assert data.dates[-1] == pd.Timestamp("2026-09-30")
    for name in ("close", "cumadj"):
        path = feather_directory / (name + ".feather")
        frame = pd.read_feather(path)
        frame.iloc[-1, 1:] = 1e100
        frame.to_feather(path)
    after = MarketData(feather_directory).feature("close")
    np.testing.assert_allclose(before, after)


def test_caches_release_when_data_object_is_released(feather_directory):
    data = MarketData(feather_directory)
    data.feature("vwap")
    reference = weakref.ref(data)
    del data
    gc.collect()
    assert reference() is None


def test_mismatched_axes_fail_without_silent_alignment(feather_directory):
    path = feather_directory / "open.feather"
    frame = pd.read_feather(path)
    frame = frame[["date", "300001.SZ", "600001.SH", "000001.SZ"]]
    frame.to_feather(path)
    with pytest.raises(ValueError, match="different dates or stock columns"):
        MarketData(feather_directory).feature("open")


def test_strict_proxy_refusal(feather_directory):
    with pytest.raises(ValueError, match="unavailable"):
        MarketData(feather_directory, strict_features=True).feature("vwap")


def test_forward_labels_use_next_open_and_actual_exit(feather_directory):
    data = MarketData(feather_directory)
    op = data.feature("open")
    labels = data.forward_returns(1)
    np.testing.assert_allclose(labels[0], op[2] / op[1] - 1)
    assert np.isnan(labels[-2:]).all()
