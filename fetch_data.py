"""
fetch_data.py — Headless WRTS data fetch script
Reads students.txt, fetches all student data from info.grad.ku.ac.th,
and writes results to wrts_cache.json atomically.

Designed to be run by Windows Task Scheduler (weekly + on startup).
Exit codes:
  0 — success (all students fetched without error)
  1 — partial success (one or more student fetches failed)
  2 — fatal error (students.txt missing, cache write failed, etc.)
"""

import json
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import tracker

# ── File paths (relative to this script) ──────────────────────────────────────

_BASE = Path(__file__).parent
STUDENTS_FILE = _BASE / "students.txt"
CACHE_FILE    = _BASE / "wrts_cache.json"
LOCK_FILE     = _BASE / ".fetch.lock"
LOG_FILE      = _BASE / "wrts_fetch.log"

# ── Logging setup ──────────────────────────────────────────────────────────────

def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("wrts_fetch")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        # Rotating file handler — 1 MB max, keep 1 backup
        fh = RotatingFileHandler(
            LOG_FILE, maxBytes=1_000_000, backupCount=1, encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)

        # Console handler for interactive runs
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(ch)

    return logger


log = _setup_logging()


# ── Core helpers ───────────────────────────────────────────────────────────────

def read_student_ids(path: str) -> list[str]:
    """
    Read student IDs from a text file.
    Skips blank lines and lines starting with '#'.
    Returns only digit-only strings of length 8–12.
    Raises FileNotFoundError if the file does not exist.
    """
    ids = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Take first token (handles "id, name" or "id name" formats)
            parts = line.split(",")[0].split()
            if not parts:
                continue
            token = parts[0]
            if token.isdigit() and 8 <= len(token) <= 12:
                ids.append(token)
    return ids


def acquire_lock(lock_path: str) -> bool:
    """
    Attempt to create a lock file exclusively.
    Returns True if the lock was acquired, False if it already exists.
    """
    try:
        # O_CREAT | O_EXCL — atomic create, fails if file exists
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False


def release_lock(lock_path: str) -> None:
    """
    Remove the lock file. Silently ignores FileNotFoundError.
    """
    try:
        os.remove(str(lock_path))
    except FileNotFoundError:
        pass


def write_cache_atomic(data: dict, cache_path: str) -> None:
    """
    Write data to cache_path atomically using a temp file + rename.
    Ensures the cache is never left in a partial state.
    """
    cache_path = Path(cache_path)
    tmp_path = cache_path.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(str(tmp_path), str(cache_path))
    except Exception:
        # Clean up temp file if rename failed
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def append_log(log_path: str, entry: dict) -> None:
    """
    Append one JSON-lines entry to the log file.
    Rotates the log file if it exceeds 1 MB (renames to .log.1).
    """
    log_path = Path(log_path)

    # Rotate if over 1 MB
    if log_path.exists() and log_path.stat().st_size > 1_000_000:
        rotated = log_path.with_suffix(".log.1")
        try:
            os.replace(str(log_path), str(rotated))
        except OSError:
            pass  # Best-effort rotation

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Main orchestration ─────────────────────────────────────────────────────────

def main() -> int:
    start_time = datetime.now()
    run_id = start_time.isoformat(timespec="seconds")
    log.info(f"=== WRTS fetch run started: {run_id} ===")

    # ── Acquire lock ──
    if not acquire_lock(str(LOCK_FILE)):
        log.warning("Lock file already present — another fetch run may be in progress. Skipping.")
        return 0

    n_students = 0
    n_errors = 0
    exit_code = 0

    try:
        # ── Read student IDs ──
        try:
            ids = read_student_ids(str(STUDENTS_FILE))
        except FileNotFoundError:
            log.error(f"students.txt not found at {STUDENTS_FILE}")
            _write_failure_log(run_id, start_time, 0, 0, "failure")
            return 2
        except OSError as e:
            log.error(f"Cannot read students.txt: {e}")
            _write_failure_log(run_id, start_time, 0, 0, "failure")
            return 2

        if not ids:
            log.warning("No valid student IDs found in students.txt — nothing to fetch.")
            _write_failure_log(run_id, start_time, 0, 0, "failure")
            return 2

        n_students = len(ids)
        log.info(f"Fetching data for {n_students} students…")

        # ── Fetch all students ──
        def _progress(i: int, total: int, sid: str) -> None:
            log.info(f"  [{i+1}/{total}] Fetching {sid}...")

        results = tracker.fetch_multiple(ids, progress_callback=_progress, delay=1.5)

        # Count errors
        n_errors = sum(1 for r in results.values() if r.get("error"))
        if n_errors:
            log.warning(f"{n_errors}/{n_students} student fetches returned errors.")
            exit_code = 1
        else:
            log.info(f"All {n_students} students fetched successfully.")

        # ── Merge with existing cache (preserve deleted records) ──
        from cache_utils import load_cache, merge_results_with_cache
        existing_cache = load_cache(CACHE_FILE)
        if isinstance(existing_cache, dict):
            log.info("Merging fresh results with existing cache...")
            merged_data = merge_results_with_cache(results, existing_cache)
        else:
            merged_data = results

        # ── Build and write cache ──
        end_time = datetime.now()
        status = "success" if n_errors == 0 else "partial"

        cache = {
            "meta": {
                "last_run":       end_time.isoformat(timespec="seconds"),
                "students":       n_students,
                "errors":         n_errors,
                "status":         status,
                "schema_version": 1,
            },
            "data": merged_data,
        }

        try:
            write_cache_atomic(cache, str(CACHE_FILE))
            log.info(f"Cache written to {CACHE_FILE}")
        except OSError as e:
            log.error(f"Failed to write cache: {e}")
            _write_failure_log(run_id, start_time, n_students, n_errors, "failure")
            return 2

        # ── Append structured log entry ──
        log_entry = {
            "run_id":   run_id,
            "start":    start_time.isoformat(timespec="seconds"),
            "end":      end_time.isoformat(timespec="seconds"),
            "students": n_students,
            "errors":   n_errors,
            "status":   status,
        }
        append_log(str(LOG_FILE), log_entry)
        log.info(f"=== Run complete: {status} ({n_students} students, {n_errors} errors) ===")

        return exit_code

    except Exception as e:
        log.exception(f"Unhandled exception during fetch run: {e}")
        _write_failure_log(run_id, start_time, n_students, n_errors, "failure")
        return 2

    finally:
        release_lock(str(LOCK_FILE))


def _write_failure_log(run_id: str, start: datetime, students: int, errors: int, status: str) -> None:
    """Write a failure log entry. Best-effort — does not raise."""
    try:
        entry = {
            "run_id":   run_id,
            "start":    start.isoformat(timespec="seconds"),
            "end":      datetime.now().isoformat(timespec="seconds"),
            "students": students,
            "errors":   errors,
            "status":   status,
        }
        append_log(str(LOG_FILE), entry)
    except Exception:
        pass


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(main())
