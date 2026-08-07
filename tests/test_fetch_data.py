"""
tests/test_fetch_data.py
Unit and property-based tests for fetch_data.py helpers.

Covers:
  - read_student_ids
  - acquire_lock / release_lock
  - write_cache_atomic
  - append_log
  - Property 2: Atomic write leaves no partial state
  - Property 3: Student ID parsing filters correctly
  - Property 4: Lock prevents concurrent runs
  - Property 6: Log entry completeness
"""

import json
import os
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, assume, settings
from hypothesis import strategies as st

import fetch_data


# ══════════════════════════════════════════════════════════════════
# Helpers / strategies
# ══════════════════════════════════════════════════════════════════

def _valid_sid() -> st.SearchStrategy:
    """Generate valid student ID strings (8–12 digit strings)."""
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


def _log_entry_strategy() -> st.SearchStrategy:
    ts = st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31),
    ).map(lambda d: d.isoformat(timespec="seconds"))
    return st.fixed_dictionaries({
        "run_id":   ts,
        "start":    ts,
        "end":      ts,
        "students": st.integers(min_value=0, max_value=200),
        "errors":   st.integers(min_value=0, max_value=200),
        "status":   st.sampled_from(["success", "partial", "failure"]),
    })


# ══════════════════════════════════════════════════════════════════
# read_student_ids — unit tests
# ══════════════════════════════════════════════════════════════════

class TestReadStudentIds:
    def test_valid_file(self, sample_students_file):
        ids = fetch_data.read_student_ids(str(sample_students_file))
        assert ids == ["6514500009", "6814500001"]

    def test_skips_comments_and_blanks(self, tmp_path):
        f = tmp_path / "s.txt"
        f.write_text("# comment\n\n6514500009\n# another\n6814500001\n", encoding="utf-8")
        ids = fetch_data.read_student_ids(str(f))
        assert ids == ["6514500009", "6814500001"]

    def test_absent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            fetch_data.read_student_ids(str(tmp_path / "nonexistent.txt"))

    def test_non_digit_lines_excluded(self, tmp_path):
        f = tmp_path / "s.txt"
        f.write_text("abc\n6514500009\nhello world\n", encoding="utf-8")
        ids = fetch_data.read_student_ids(str(f))
        assert ids == ["6514500009"]

    def test_too_short_excluded(self, tmp_path):
        f = tmp_path / "s.txt"
        f.write_text("1234567\n6514500009\n", encoding="utf-8")  # 7 digits — too short
        ids = fetch_data.read_student_ids(str(f))
        assert ids == ["6514500009"]

    def test_too_long_excluded(self, tmp_path):
        f = tmp_path / "s.txt"
        f.write_text("1234567890123\n6514500009\n", encoding="utf-8")  # 13 digits — too long
        ids = fetch_data.read_student_ids(str(f))
        assert ids == ["6514500009"]

    def test_csv_format_first_token(self, tmp_path):
        f = tmp_path / "s.txt"
        f.write_text("6514500009, Test Student\n6814500001,Another\n", encoding="utf-8")
        ids = fetch_data.read_student_ids(str(f))
        assert ids == ["6514500009", "6814500001"]

    def test_empty_file_returns_empty_list(self, tmp_path):
        f = tmp_path / "s.txt"
        f.write_text("", encoding="utf-8")
        ids = fetch_data.read_student_ids(str(f))
        assert ids == []


# ══════════════════════════════════════════════════════════════════
# acquire_lock / release_lock — unit tests
# ══════════════════════════════════════════════════════════════════

class TestLock:
    def test_acquire_creates_file(self, tmp_path):
        lock = str(tmp_path / ".fetch.lock")
        result = fetch_data.acquire_lock(lock)
        assert result is True
        assert os.path.exists(lock)

    def test_acquire_returns_false_when_exists(self, tmp_path):
        lock = str(tmp_path / ".fetch.lock")
        fetch_data.acquire_lock(lock)
        result = fetch_data.acquire_lock(lock)
        assert result is False

    def test_release_removes_file(self, tmp_path):
        lock = str(tmp_path / ".fetch.lock")
        fetch_data.acquire_lock(lock)
        fetch_data.release_lock(lock)
        assert not os.path.exists(lock)

    def test_release_silent_when_absent(self, tmp_path):
        lock = str(tmp_path / ".fetch.lock")
        # Should not raise
        fetch_data.release_lock(lock)

    def test_acquire_release_cycle(self, tmp_path):
        lock = str(tmp_path / ".fetch.lock")
        assert fetch_data.acquire_lock(lock) is True
        assert fetch_data.acquire_lock(lock) is False
        fetch_data.release_lock(lock)
        assert fetch_data.acquire_lock(lock) is True


# ══════════════════════════════════════════════════════════════════
# write_cache_atomic — unit tests
# ══════════════════════════════════════════════════════════════════

class TestWriteCacheAtomic:
    def test_writes_valid_json(self, tmp_path, sample_cache_dict):
        cache_path = str(tmp_path / "wrts_cache.json")
        fetch_data.write_cache_atomic(sample_cache_dict, cache_path)
        result = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        assert result == sample_cache_dict

    def test_no_tmp_file_after_success(self, tmp_path, sample_cache_dict):
        cache_path = str(tmp_path / "wrts_cache.json")
        fetch_data.write_cache_atomic(sample_cache_dict, cache_path)
        assert not (tmp_path / "wrts_cache.json.tmp").exists()

    def test_overwrites_existing_file(self, tmp_path, sample_cache_dict):
        cache_path = str(tmp_path / "wrts_cache.json")
        # Write initial content
        Path(cache_path).write_text('{"old": true}', encoding="utf-8")
        fetch_data.write_cache_atomic(sample_cache_dict, cache_path)
        result = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        assert result == sample_cache_dict

    def test_unicode_preserved(self, tmp_path):
        cache_path = str(tmp_path / "wrts_cache.json")
        data = {"meta": {}, "data": {"6514500009": {"name_th": "ทดสอบ นามสกุล"}}}
        fetch_data.write_cache_atomic(data, cache_path)
        text = Path(cache_path).read_text(encoding="utf-8")
        assert "ทดสอบ นามสกุล" in text


# ══════════════════════════════════════════════════════════════════
# append_log — unit tests
# ══════════════════════════════════════════════════════════════════

class TestAppendLog:
    def _make_entry(self) -> dict:
        now = datetime.now().isoformat(timespec="seconds")
        return {
            "run_id":   now,
            "start":    now,
            "end":      now,
            "students": 5,
            "errors":   0,
            "status":   "success",
        }

    def test_creates_file_and_appends(self, tmp_path):
        log_path = str(tmp_path / "wrts_fetch.log")
        entry = self._make_entry()
        fetch_data.append_log(log_path, entry)
        lines = Path(log_path).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0]) == entry

    def test_appends_multiple_entries(self, tmp_path):
        log_path = str(tmp_path / "wrts_fetch.log")
        for _ in range(3):
            fetch_data.append_log(log_path, self._make_entry())
        lines = Path(log_path).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

    def test_rotates_when_over_1mb(self, tmp_path):
        log_path = tmp_path / "wrts_fetch.log"
        rotated_path = tmp_path / "wrts_fetch.log.1"
        # Write a file just over 1 MB
        log_path.write_bytes(b"x" * 1_000_001)
        entry = self._make_entry()
        fetch_data.append_log(str(log_path), entry)
        # Original content should be in .log.1
        assert rotated_path.exists()
        # New log should contain only the new entry
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0]) == entry

    def test_no_rotation_under_1mb(self, tmp_path):
        log_path = tmp_path / "wrts_fetch.log"
        rotated_path = tmp_path / "wrts_fetch.log.1"
        log_path.write_bytes(b"x" * 999_999)
        fetch_data.append_log(str(log_path), self._make_entry())
        assert not rotated_path.exists()


# ══════════════════════════════════════════════════════════════════
# Property 2: Atomic write leaves no partial state
# ══════════════════════════════════════════════════════════════════

@given(_cache_dict_strategy(), _cache_dict_strategy())
@settings(max_examples=50, suppress_health_check=[])
def test_property2_atomic_write(old_cache, new_cache):
    """
    Property 2: After write_cache_atomic completes, the file contains
    exactly the new data and no .tmp file remains.
    """
    import tempfile, shutil
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        cache_path = tmp_dir / "wrts_cache.json"
        # Write old cache first
        fetch_data.write_cache_atomic(old_cache, str(cache_path))
        # Overwrite with new cache
        fetch_data.write_cache_atomic(new_cache, str(cache_path))
        # File must equal new_cache exactly
        result = json.loads(cache_path.read_text(encoding="utf-8"))
        assert result == new_cache
        # No temp file should remain
        assert not (tmp_dir / "wrts_cache.json.tmp").exists()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════
# Property 3: Student ID parsing filters correctly
# ══════════════════════════════════════════════════════════════════

@given(st.lists(st.text(max_size=20), max_size=30))
@settings(max_examples=100, suppress_health_check=[])
def test_property3_id_parsing(lines):
    """
    Property 3: read_student_ids returns only digit-only strings of
    length 8–12, never blank lines or #-prefixed lines.
    """
    import tempfile, shutil
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        content = "\n".join(lines)
        f = tmp_dir / "students.txt"
        f.write_text(content, encoding="utf-8")
        result = fetch_data.read_student_ids(str(f))
        for sid in result:
            assert sid.isdigit(), f"Non-digit ID returned: {sid!r}"
            assert 8 <= len(sid) <= 12, f"ID length out of range: {sid!r}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════
# Property 4: Lock prevents concurrent runs
# ══════════════════════════════════════════════════════════════════

def test_property4_lock_prevents_concurrent_runs(tmp_path):
    """
    Property 4: When a lock file is already present, acquire_lock returns
    False and the cache must not be modified.
    """
    lock_path = str(tmp_path / ".fetch.lock")
    cache_path = tmp_path / "wrts_cache.json"
    original_content = '{"meta": {}, "data": {}}'
    cache_path.write_text(original_content, encoding="utf-8")

    # Pre-create the lock file
    fetch_data.acquire_lock(lock_path)

    # Second acquire must fail
    result = fetch_data.acquire_lock(lock_path)
    assert result is False

    # Cache must be unchanged
    assert cache_path.read_text(encoding="utf-8") == original_content


# ══════════════════════════════════════════════════════════════════
# Property 6: Log entry completeness
# ══════════════════════════════════════════════════════════════════

@given(_log_entry_strategy())
@settings(max_examples=100, suppress_health_check=[])
def test_property6_log_entry_completeness(entry):
    """
    Property 6: Every appended log entry contains all required fields
    with correct types.
    """
    import tempfile, shutil
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        log_path = str(tmp_dir / "wrts_fetch.log")
        fetch_data.append_log(log_path, entry)
        lines = Path(log_path).read_text(encoding="utf-8").strip().splitlines()
        parsed = json.loads(lines[-1])

        required = {"run_id", "start", "end", "students", "errors", "status"}
        assert required.issubset(parsed.keys()), f"Missing fields: {required - parsed.keys()}"
        assert isinstance(parsed["students"], int)
        assert isinstance(parsed["errors"], int)
        assert parsed["status"] in ("success", "partial", "failure")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
