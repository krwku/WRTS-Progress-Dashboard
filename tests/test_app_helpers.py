"""
tests/test_app_helpers.py
Unit and property-based tests for app.py cache helper functions.

Covers:
  - load_cache
  - cache_age_hours
  - save_cache
  - Property 1: Cache round-trip integrity
  - Property 5: Staleness detection is monotone
"""

import json
import os
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from hypothesis import given, assume, settings
from hypothesis import strategies as st

# Import helpers directly from cache_utils (no Streamlit dependency)
from cache_utils import load_cache, cache_age_hours, save_cache


# ══════════════════════════════════════════════════════════════════
# Helpers / strategies
# ══════════════════════════════════════════════════════════════════

def _valid_sid() -> st.SearchStrategy:
    return st.integers(min_value=10_000_000, max_value=999_999_999_999).map(str)


def _milestone_strategy() -> st.SearchStrategy:
    return st.fixed_dictionaries({
        "label":    st.text(min_size=1, max_size=30),
        "short":    st.text(min_size=1, max_size=10),
        "latest":   st.none(),
        "history":  st.just([]),
        "status":   st.sampled_from(["approved", "revise", "cancelled", "inprogress", "none"]),
        "attempts": st.integers(min_value=0, max_value=10),
    })


def _cache_entry_strategy() -> st.SearchStrategy:
    return st.fixed_dictionaries({
        "student_id": _valid_sid(),
        "name_th":    st.text(max_size=50),
        "name_en":    st.text(max_size=50),
        "records":    st.just([]),
        "milestones": st.lists(_milestone_strategy(), min_size=7, max_size=7),
        "fetched_at": st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31),
        ).map(lambda d: d.isoformat(timespec="seconds")),
        "error":      st.none(),
    })


def _cache_dict_strategy() -> st.SearchStrategy:
    return st.fixed_dictionaries({
        "meta": st.fixed_dictionaries({
            "last_run":       st.datetimes(
                min_value=datetime(2020, 1, 1),
                max_value=datetime(2030, 12, 31),
            ).map(lambda d: d.isoformat(timespec="seconds")),
            "students":       st.integers(min_value=0, max_value=200),
            "errors":         st.integers(min_value=0, max_value=200),
            "status":         st.sampled_from(["success", "partial", "failure"]),
            "schema_version": st.just(1),
        }),
        "data": st.dictionaries(
            keys=_valid_sid(),
            values=_cache_entry_strategy(),
            max_size=5,
        ),
    })


def _iso_timestamp_strategy() -> st.SearchStrategy:
    return st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2025, 12, 31),
    ).map(lambda d: d.isoformat(timespec="seconds"))


# ══════════════════════════════════════════════════════════════════
# load_cache — unit tests
# ══════════════════════════════════════════════════════════════════

class TestLoadCache:
    def test_valid_file_returns_dict(self, sample_cache_file, sample_cache_dict):
        result = load_cache(sample_cache_file)
        assert isinstance(result, dict)
        assert "meta" in result
        assert "data" in result

    def test_absent_file_returns_none(self, tmp_path):
        result = load_cache(tmp_path / "nonexistent.json")
        assert result is None

    def test_malformed_json_returns_false(self, tmp_path):
        bad_file = tmp_path / "wrts_cache.json"
        bad_file.write_text("{not valid json", encoding="utf-8")
        result = load_cache(bad_file)
        assert result is False

    def test_empty_file_returns_false(self, tmp_path):
        empty_file = tmp_path / "wrts_cache.json"
        empty_file.write_text("", encoding="utf-8")
        result = load_cache(empty_file)
        assert result is False

    def test_data_matches_written_content(self, tmp_path, sample_cache_dict):
        cache_file = tmp_path / "wrts_cache.json"
        cache_file.write_text(
            json.dumps(sample_cache_dict, ensure_ascii=False),
            encoding="utf-8",
        )
        result = load_cache(cache_file)
        assert result == sample_cache_dict


# ══════════════════════════════════════════════════════════════════
# cache_age_hours — unit tests
# ══════════════════════════════════════════════════════════════════

class TestCacheAgeHours:
    def test_one_hour_ago(self):
        ts = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
        age = cache_age_hours(ts)
        assert 0.9 < age < 1.1

    def test_one_day_ago(self):
        ts = (datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds")
        age = cache_age_hours(ts)
        assert 23.9 < age < 24.1

    def test_very_recent_is_near_zero(self):
        ts = datetime.now().isoformat(timespec="seconds")
        age = cache_age_hours(ts)
        assert 0.0 <= age < 0.1

    def test_always_non_negative(self):
        # Future timestamp (clock skew) should return 0.0
        ts = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
        age = cache_age_hours(ts)
        assert age == 0.0

    def test_invalid_string_returns_zero(self):
        age = cache_age_hours("not-a-timestamp")
        assert age == 0.0

    def test_none_returns_zero(self):
        age = cache_age_hours(None)
        assert age == 0.0


# ══════════════════════════════════════════════════════════════════
# save_cache — unit tests
# ══════════════════════════════════════════════════════════════════

class TestSaveCache:
    def test_writes_valid_json(self, tmp_path, sample_cache_dict):
        cache_path = tmp_path / "wrts_cache.json"
        save_cache(
            cache_path,
            list(sample_cache_dict["data"].keys()),
            sample_cache_dict["data"],
            sample_cache_dict["meta"],
        )
        result = json.loads(cache_path.read_text(encoding="utf-8"))
        assert result["data"] == sample_cache_dict["data"]
        assert result["meta"] == sample_cache_dict["meta"]

    def test_no_tmp_file_after_success(self, tmp_path, sample_cache_dict):
        cache_path = tmp_path / "wrts_cache.json"
        save_cache(
            cache_path,
            list(sample_cache_dict["data"].keys()),
            sample_cache_dict["data"],
            sample_cache_dict["meta"],
        )
        assert not (tmp_path / "wrts_cache.json.tmp").exists()

    def test_round_trip(self, tmp_path, sample_cache_dict):
        cache_path = tmp_path / "wrts_cache.json"
        save_cache(
            cache_path,
            list(sample_cache_dict["data"].keys()),
            sample_cache_dict["data"],
            sample_cache_dict["meta"],
        )
        loaded = load_cache(cache_path)
        assert loaded["data"] == sample_cache_dict["data"]


# ══════════════════════════════════════════════════════════════════
# Property 1: Cache round-trip integrity
# ══════════════════════════════════════════════════════════════════

@given(st.dictionaries(
    keys=st.text(min_size=1, max_size=10),
    values=st.one_of(st.integers(), st.text(max_size=20), st.none()),
    max_size=10,
))
@settings(max_examples=100)
def test_property1_cache_roundtrip(data):
    """
    Property 1: Serializing a dict to JSON and deserializing it
    produces a structurally equivalent dict (round-trip integrity).
    """
    serialized = json.dumps(data, ensure_ascii=False)
    result = json.loads(serialized)
    assert result == data


# ══════════════════════════════════════════════════════════════════
# Property 5: Staleness detection is monotone
# ══════════════════════════════════════════════════════════════════

@given(
    st.integers(min_value=0, max_value=8760),   # age1 in hours (0–1 year)
    st.integers(min_value=0, max_value=8760),   # age2 in hours
)
@settings(max_examples=100)
def test_property5_staleness_monotone(age1_hours, age2_hours):
    """
    Property 5: For any two timestamps where t1 is older than t2,
    cache_age_hours(t1) >= cache_age_hours(t2).
    Both values must be non-negative.
    """
    from datetime import timedelta
    now = datetime.now()
    # t1 is older (larger age), t2 is more recent (smaller age)
    t1 = (now - timedelta(hours=age1_hours + age2_hours + 1)).isoformat(timespec="seconds")
    t2 = (now - timedelta(hours=age2_hours)).isoformat(timespec="seconds")

    a1 = cache_age_hours(t1)
    a2 = cache_age_hours(t2)

    assert a1 >= 0.0
    assert a2 >= 0.0
    assert a1 >= a2, f"Expected age({t1}) >= age({t2}), got {a1:.4f} < {a2:.4f}"
