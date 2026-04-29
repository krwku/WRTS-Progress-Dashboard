"""
tracker.py — WRTS scraper module
Fetches and parses student progress from https://info.grad.ku.ac.th/track/
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time

URL = "https://info.grad.ku.ac.th/track/index.php"

MILESTONES = [
    {"label": "แต่งตั้งกรรมการ",               "short": "กรรมการ",       "keywords": ["ขอแต่งตั้งคณะกรรมการประจำตัวนิสิต"]},
    {"label": "อนุมัติโครงการ (iThesis)",       "short": "โครงการ",       "keywords": ["ขออนุมัติโครงการวิทยานิพนธ์"]},
    {"label": "รายงานผลการเรียน",              "short": "ผลการเรียน",     "keywords": ["รายงานผลการเรียนตามหลักสูตร"]},
    {"label": "แต่งตั้งประธาน/ผู้ทรงคุณวุฒิ",  "short": "ประธาน",        "keywords": ["แต่งตั้งประธานการสอบ", "ผู้ทรงคุณวุฒิภายนอก"]},
    {"label": "หนังสือนัดสอบ",                 "short": "นัดสอบ",         "keywords": ["หนังสือนัดสอบ"]},
    {"label": "ส่งต้นฉบับวิทยานิพนธ์",         "short": "ต้นฉบับ",        "keywords": ["ส่งต้นฉบับวิทยานิพนธ์"]},
    {"label": "หนังสือรับรองสภาอนุมัติ",        "short": "สภาอนุมัติ",     "keywords": ["หนังสือรับรองฉบับสภาอนุมัติ"]},
]

RESULT_MAP = {
    "อนุมัติ": "approved",
    "ผ่าน":   "approved",
    "แก้ไข":  "revise",
    "ยกเลิก": "cancelled",
}


def classify_result(result_text: str) -> str:
    if not result_text:
        return "inprogress"
    for kw, status in RESULT_MAP.items():
        if kw in result_text:
            return status
    return "inprogress"


def build_milestones(records: list) -> list:
    """
    Match records to milestones. Records are newest-first from HTML.
    First match = most recent submission for that milestone.
    """
    matched = set()
    out = []
    for m in MILESTONES:
        hits = [r for r in records if any(kw in r["topic"] for kw in m["keywords"])]
        latest  = hits[0] if hits else None
        history = hits[1:] if hits else []
        for r in hits:
            matched.add(r["request_no"])
        out.append({
            "label":   m["label"],
            "short":   m["short"],
            "latest":  latest,
            "history": history,
            "status":  classify_result(latest["result"]) if latest else "none",
            "attempts": len(hits),
        })
    return out


def parse_html(html: str, student_id: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    name_th, name_en = "", ""
    name_div = soup.find("div", class_=lambda c: c and "fontsize175" in c and "color-font" in c)
    if name_div:
        text = name_div.get_text(" ", strip=True)
        if "ชื่อ - สกุล :" in text:
            name_th = text.split("ชื่อ - สกุล :")[1].split("Name-Surname")[0].strip()
        if "Name-Surname :" in text:
            name_en = text.split("Name-Surname :")[1].strip()

    records = []
    for row in soup.find_all("div", style=lambda s: s and "padding-top" in (s or "")):
        cols = row.find_all("div", recursive=False)
        if len(cols) < 7:
            continue
        req_no = cols[0].get_text(strip=True)
        if not req_no.startswith("B"):
            continue
        records.append({
            "request_no":  req_no,
            "topic":       cols[1].get_text(strip=True),
            "issue_date":  cols[2].get_text(strip=True),
            "due_date":    cols[3].get_text(strip=True),
            "status":      cols[4].get_text(strip=True),
            "finish_date": cols[5].get_text(strip=True),
            "result":      cols[6].get_text(" ", strip=True),
        })

    milestones = build_milestones(records)

    return {
        "student_id": student_id,
        "name_th":    name_th,
        "name_en":    name_en,
        "records":    records,
        "milestones": milestones,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "error":      None,
    }


def fetch_student(student_id: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0", "Referer": URL}
    payload = {
        "SearchType": "2",
        "txtSearch": student_id.strip(),
        "SubmitSearch": "ค้นหา / search",
    }
    try:
        resp = requests.post(URL, data=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return parse_html(resp.text, student_id)
    except requests.RequestException as e:
        return {
            "student_id": student_id,
            "name_th": "", "name_en": "",
            "records": [], "milestones": [],
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "error": str(e),
        }


def fetch_multiple(student_ids: list, progress_callback=None, delay: float = 1.5) -> dict:
    """
    Fetch multiple students. progress_callback(i, total, sid) called each step.
    Returns dict keyed by student_id.
    """
    results = {}
    for i, sid in enumerate(student_ids):
        if progress_callback:
            progress_callback(i, len(student_ids), sid)
        results[sid] = fetch_student(sid)
        if i < len(student_ids) - 1:
            time.sleep(delay)
    return results
