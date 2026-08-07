"""
conftest.py — shared pytest fixtures for auto-scheduler-local-cache tests
"""

import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta

from hypothesis import settings

# ── Hypothesis profile ─────────────────────────────────────────────────────────
# Several property tests do real filesystem I/O. Hypothesis' default 200 ms
# per-example deadline makes them flaky on slower disks and in containers, so
# disable it — these tests assert on behaviour, not on latency.

settings.register_profile("wrts", deadline=None)
settings.load_profile("wrts")


# ── Sample data ────────────────────────────────────────────────────────────────

SAMPLE_STUDENT_IDS = ["6514500009", "6814500001"]

SAMPLE_MILESTONE = {
    "label": "แต่งตั้งกรรมการ",
    "short": "กรรมการ",
    "latest": None,
    "history": [],
    "status": "none",
    "attempts": 0,
}

SAMPLE_CACHE_ENTRY = {
    "student_id": "6514500009",
    "name_th": "ทดสอบ นามสกุล",
    "name_en": "Test Student",
    "records": [],
    "milestones": [SAMPLE_MILESTONE] * 7,
    "fetched_at": (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds"),
    "error": None,
}

SAMPLE_CACHE_META = {
    "last_run": datetime.now().isoformat(timespec="seconds"),
    "students": 2,
    "errors": 0,
    "status": "success",
    "schema_version": 1,
}

SAMPLE_CACHE_DICT = {
    "meta": SAMPLE_CACHE_META,
    "data": {
        "6514500009": SAMPLE_CACHE_ENTRY,
    },
}


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory for file-based tests."""
    return tmp_path


@pytest.fixture
def sample_students_file(tmp_path):
    """Write a sample students.txt to a temp directory and return its path."""
    content = (
        "# รายชื่อนิสิต\n"
        "# comment line\n"
        "\n"
        "6514500009\n"
        "6814500001\n"
    )
    p = tmp_path / "students.txt"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def sample_cache_file(tmp_path):
    """Write a valid wrts_cache.json to a temp directory and return its path."""
    p = tmp_path / "wrts_cache.json"
    p.write_text(
        json.dumps(SAMPLE_CACHE_DICT, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p


@pytest.fixture
def sample_cache_dict():
    """Return a deep copy of the sample cache dict."""
    import copy
    return copy.deepcopy(SAMPLE_CACHE_DICT)
