"""
cache_utils.py — Cache helper functions shared by app.py and tests.
No Streamlit dependency — safe to import in any context.
"""

import json
import os
from datetime import datetime
from pathlib import Path


def load_cache(cache_path: Path) -> "dict | None | bool":
    """
    Read wrts_cache.json.
    Returns:
      - dict   if file exists and is valid JSON
      - None   if file does not exist
      - False  if file exists but is malformed / unreadable
    """
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError):
        return False


def cache_age_hours(fetched_at: str) -> float:
    """
    Return hours elapsed since the fetched_at ISO 8601 timestamp.
    Always returns a non-negative value (clamps to 0.0 on clock skew or bad input).
    """
    try:
        dt = datetime.fromisoformat(fetched_at)
        age = (datetime.now() - dt).total_seconds() / 3600
        return max(0.0, age)
    except (ValueError, TypeError):
        return 0.0


def merge_student_records(cached_entry: dict, fresh_entry: dict) -> dict:
    """
    Merge a freshly fetched student entry with the previously cached one.

    Strategy:
    - Start with all records from the cached entry (preserves history).
    - For each record in the fresh entry, update the cached version if the
      request_no already exists (status/result may have changed), or add it
      if it is new.
    - Re-run build_milestones on the merged record list so milestone statuses
      reflect the latest data.
    - Always use the fresh entry's name, fetched_at, and error fields.

    This ensures records deleted from the server are never lost.
    """
    import tracker as tr

    # If the fresh fetch errored, keep the cached data but update fetched_at
    if fresh_entry.get("error"):
        return fresh_entry

    # Build a dict of cached records keyed by request_no
    cached_records = {r["request_no"]: r for r in (cached_entry.get("records") or [])}

    # Overlay fresh records (update existing, add new)
    for r in fresh_entry.get("records") or []:
        cached_records[r["request_no"]] = r

    # Restore original order: fresh records first (newest), then any
    # cached-only records appended at the end (oldest / deleted from server)
    fresh_nos = [r["request_no"] for r in (fresh_entry.get("records") or [])]
    fresh_set = set(fresh_nos)
    merged_records = list(fresh_entry.get("records") or []) + [
        cached_records[no] for no in cached_records if no not in fresh_set
    ]

    # Rebuild milestones from the merged record list
    merged_milestones = tr.build_milestones(merged_records)

    return {
        "student_id": fresh_entry["student_id"],
        "name_th":    fresh_entry.get("name_th") or cached_entry.get("name_th", ""),
        "name_en":    fresh_entry.get("name_en") or cached_entry.get("name_en", ""),
        "records":    merged_records,
        "milestones": merged_milestones,
        "fetched_at": fresh_entry["fetched_at"],
        "error":      None,
    }


def merge_results_with_cache(fresh_results: dict, existing_cache: dict) -> dict:
    """
    Merge a full set of fresh fetch results with the existing cache data dict.
    Returns a new data dict with merged entries for all students.
    """
    existing_data = existing_cache.get("data", {}) if existing_cache else {}
    merged = {}
    for sid, fresh_entry in fresh_results.items():
        cached_entry = existing_data.get(sid, {})
        if cached_entry:
            merged[sid] = merge_student_records(cached_entry, fresh_entry)
        else:
            merged[sid] = fresh_entry
    return merged


def save_cache(cache_path: Path, students: list, data: dict, meta: dict) -> None:
    """
    Write updated data back to cache_path atomically (temp file + rename).
    Raises OSError if the write fails.
    """
    payload = {"meta": meta, "data": data}
    tmp_path = cache_path.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(str(tmp_path), str(cache_path))
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise
