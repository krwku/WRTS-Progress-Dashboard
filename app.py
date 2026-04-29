"""
app.py — WRTS Progress Dashboard (Streamlit Cloud)
Deploy at: https://share.streamlit.io
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json
import io
from pathlib import Path

import tracker as tr

# ─── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="WRTS Dashboard — KU Graduate School",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Sarabun', sans-serif !important;
}

/* Milestone badge grid */
.ms-grid { display: flex; gap: 4px; flex-wrap: wrap; }
.ms-badge {
    display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 6px; font-size: 14px;
    cursor: default;
}
.ms-badge.approved   { background: rgba(16,185,129,0.2); }
.ms-badge.revise     { background: rgba(245,158,11,0.2); }
.ms-badge.cancelled  { background: rgba(239,68,68,0.2); }
.ms-badge.inprogress { background: rgba(59,130,246,0.2); }
.ms-badge.none       { background: rgba(100,116,139,0.15); color: #475569; }

/* Metric cards */
.metric-card {
    background: #1e2333; border: 1px solid #2a3045;
    border-radius: 10px; padding: 16px 20px; text-align: center;
}
.metric-value { font-size: 2rem; font-weight: 700; line-height: 1; }
.metric-label { font-size: 0.75rem; color: #64748b; margin-top: 4px; }

/* Section headers */
.section-header {
    font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em;
    color: #64748b; margin-bottom: 8px; font-weight: 600;
}

/* Behind-average row highlight */
.behind-row { background: rgba(239,68,68,0.08) !important; }

/* Sidebar */
[data-testid="stSidebar"] { background: #111827 !important; }

/* Tab styling */
[data-testid="stTabs"] button { font-family: 'Sarabun', sans-serif !important; font-size: 0.9rem; }

/* Monospace for IDs */
.mono { font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; }

/* Year badge */
.year-badge {
    display: inline-block; background: #1a3a4a; color: #38bdf8;
    border-radius: 4px; padding: 2px 8px; font-size: 0.72rem;
    font-family: 'IBM Plex Mono', monospace; font-weight: 500;
}
</style>
""", unsafe_allow_html=True)

# ─── Constants ─────────────────────────────────────────────────────────────────

STATUS_ICON  = {"approved": "✅", "revise": "⚠️", "cancelled": "❌", "inprogress": "🔵", "none": "⬜"}
STATUS_LABEL = {"approved": "อนุมัติ/ผ่าน", "revise": "แก้ไข", "cancelled": "ยกเลิก", "inprogress": "ดำเนินการ", "none": "ยังไม่มี"}
MS_LABELS    = [m["label"] for m in tr.MILESTONES]
MS_SHORTS    = [m["short"] for m in tr.MILESTONES]
CURRENT_BE   = datetime.now().year + 543   # Buddhist Era year

TEMPLATE_TXT = """\
# รายชื่อนิสิต WRTS Tracker
# หนึ่งรหัสต่อบรรทัด  |  บรรทัดที่ขึ้นต้นด้วย # จะถูกข้าม
# ตัวอย่าง:
6514500439
6814500981
"""

DEFAULT_FILE = Path(__file__).parent / "students.txt"

# ─── Helpers ───────────────────────────────────────────────────────────────────

def _parse_id_text(text: str) -> list[str]:
    ids = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sid = line.split(",")[0].split()[0]
        if sid.isdigit() and 8 <= len(sid) <= 12:
            ids.append(sid)
    return ids

# ─── Session state init ────────────────────────────────────────────────────────

def _default_students() -> list[str]:
    if DEFAULT_FILE.exists():
        return _parse_id_text(DEFAULT_FILE.read_text(encoding="utf-8"))
    return []

for key, default in [
    ("students",     _default_students()),
    ("data",         {}),
    ("last_updated", None),
    ("fetching",     False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─── Helpers ───────────────────────────────────────────────────────────────────

def cohort_year(sid: str) -> int:
    try:
        return 2500 + int(sid[:2])
    except Exception:
        return 0

def years_enrolled(sid: str) -> int:
    cy = cohort_year(sid)
    return CURRENT_BE - cy + 1 if cy else 0

def progress_score(sid: str) -> int:
    d = st.session_state.data.get(sid, {})
    if not d or d.get("error"):
        return -1
    return sum(1 for m in d.get("milestones", []) if m["status"] == "approved")

def build_df() -> pd.DataFrame:
    rows = []
    for sid in st.session_state.students:
        d    = st.session_state.data.get(sid, {})
        cy   = cohort_year(sid)
        score = progress_score(sid)
        row = {
            "student_id":   sid,
            "cohort_be":    cy,
            "cohort_label": f"รุ่น {str(cy)[2:]}  (BE {cy})" if cy else "?",
            "years_in":     years_enrolled(sid),
            "name_th":      d.get("name_th", ""),
            "name_en":      d.get("name_en", ""),
            "score":        score,
            "fetched":      bool(d),
            "error":        bool(d.get("error")),
        }
        for i, m in enumerate(d.get("milestones", [])):
            row[f"ms_{i}"]        = m["status"]
            row[f"ms_{i}_label"]  = m["label"]
            row[f"ms_{i}_result"] = m["latest"]["result"] if m.get("latest") else ""
        rows.append(row)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


# ─── Fetch helpers ─────────────────────────────────────────────────────────────

def do_fetch(ids: list[str]):
    n = len(ids)
    bar  = st.progress(0.0, text=f"กำลังดึงข้อมูล 0/{n}…")
    msg  = st.empty()
    errors = []
    for i, sid in enumerate(ids):
        bar.progress((i + 0.5) / n, text=f"กำลังดึงข้อมูล {sid}… ({i+1}/{n})")
        result = tr.fetch_student(sid)
        st.session_state.data[sid] = result
        if result.get("error"):
            errors.append(sid)
        if i < n - 1:
            import time; time.sleep(1.5)
    bar.progress(1.0, text="เสร็จสิ้น ✓")
    st.session_state.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if errors:
        msg.warning(f"ดึงข้อมูลไม่สำเร็จ: {', '.join(errors)}")
    else:
        msg.success(f"✓ อัปเดต {n} นิสิต เมื่อ {st.session_state.last_updated}")


# ─── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🎓 WRTS Dashboard")
    st.caption("KU Graduate School Progress Tracker")
    st.divider()

    n_students = len(st.session_state.students)
    n_fetched  = sum(1 for sid in st.session_state.students if sid in st.session_state.data)

    st.markdown(f"**นิสิตในระบบ:** {n_students} คน")
    st.markdown(f"**ดึงข้อมูลแล้ว:** {n_fetched}/{n_students}")
    if st.session_state.last_updated:
        st.caption(f"อัปเดต: {st.session_state.last_updated}")
    else:
        st.caption("ยังไม่ได้ดึงข้อมูล")

    st.divider()

    if st.button("🔄 ดึงข้อมูลทั้งหมด", use_container_width=True,
                 disabled=(n_students == 0), type="primary"):
        do_fetch(st.session_state.students)
        st.rerun()

    # Refresh only unfetched
    unfetched = [s for s in st.session_state.students if s not in st.session_state.data]
    if unfetched:
        if st.button(f"⬇️ ดึงเฉพาะที่ยังไม่มีข้อมูล ({len(unfetched)})", use_container_width=True):
            do_fetch(unfetched)
            st.rerun()

    st.divider()

    # Export / Import cache
    with st.expander("💾 Export / Import ข้อมูล"):
        if st.session_state.data:
            export_payload = json.dumps(
                {"students": st.session_state.students, "data": st.session_state.data,
                 "exported_at": datetime.now().isoformat()},
                ensure_ascii=False, indent=2
            )
            st.download_button(
                "⬇️ Export ข้อมูล (.json)",
                data=export_payload,
                file_name=f"wrts_cache_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json",
            )

        imported = st.file_uploader("📂 Import ข้อมูล (.json)", type="json", key="import_cache")
        if imported:
            try:
                payload = json.load(imported)
                st.session_state.students = payload.get("students", st.session_state.students)
                st.session_state.data.update(payload.get("data", {}))
                st.success("Import สำเร็จ ✓")
                st.rerun()
            except Exception as e:
                st.error(f"Import ล้มเหลว: {e}")

    st.divider()
    st.caption("ข้อมูลจาก [info.grad.ku.ac.th](https://info.grad.ku.ac.th/track/)")
    st.caption(f"BE ปัจจุบัน: {CURRENT_BE}")


# ─── Main tabs ─────────────────────────────────────────────────────────────────

tab_mgmt, tab_dashboard, tab_analytics = st.tabs([
    "📁  จัดการรายชื่อนิสิต",
    "📊  Dashboard",
    "📈  วิเคราะห์ตามรุ่น",
])


# ══════════════════════════════════════════════════════════════════
# TAB 1 — STUDENT MANAGEMENT
# ══════════════════════════════════════════════════════════════════

with tab_mgmt:
    st.markdown("## จัดการรายชื่อนิสิต")

    col_left, col_right = st.columns([1, 1], gap="large")

    # ── LEFT: Import ──
    with col_left:
        st.markdown("### นำเข้ารายชื่อ")

        # Template download
        st.download_button(
            "📄 ดาวน์โหลด Template (students.txt)",
            data=TEMPLATE_TXT,
            file_name="students_template.txt",
            mime="text/plain",
            help="ดาวน์โหลดไฟล์ตัวอย่าง แล้วแก้ไขรหัสนิสิต",
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # Upload file
        st.markdown("**อัปโหลดไฟล์ .txt**")
        uploaded = st.file_uploader(
            "ไฟล์รายชื่อนิสิต",
            type=["txt", "csv"],
            label_visibility="collapsed",
            help="ไฟล์ .txt หรือ .csv  |  รหัสนิสิตหนึ่งรหัสต่อบรรทัด",
        )
        if uploaded:
            ids = _parse_id_text(uploaded.read().decode("utf-8"))
            if ids:
                st.success(f"พบ {len(ids)} รหัสนิสิต — กด 'บันทึก' เพื่อใช้งาน")
                st.code("\n".join(ids[:5]) + ("\n…" if len(ids) > 5 else ""), language="text")
                if st.button("✅ บันทึกรายชื่อจากไฟล์", type="primary"):
                    st.session_state.students = ids
                    st.success(f"บันทึก {len(ids)} รหัสแล้ว")
                    st.rerun()
            else:
                st.error("ไม่พบรหัสนิสิตที่ถูกต้องในไฟล์ (ต้องเป็นตัวเลข 8-12 หลัก)")

        st.markdown("---")

        # Paste text area
        st.markdown("**หรือวางรหัสนิสิตโดยตรง**")
        pasted = st.text_area(
            "รหัสนิสิต",
            label_visibility="collapsed",
            height=180,
            placeholder="6514500439\n6814500981\n...",
            help="รหัสนิสิตหนึ่งรหัสต่อบรรทัด",
        )
        if st.button("✅ บันทึกรายชื่อที่วาง"):
            ids = _parse_id_text(pasted)
            if ids:
                st.session_state.students = ids
                st.success(f"บันทึก {len(ids)} รหัสแล้ว")
                st.rerun()
            else:
                st.error("ไม่พบรหัสนิสิตที่ถูกต้อง (ต้องเป็นตัวเลข 8-12 หลัก)")

    # ── RIGHT: Current list ──
    with col_right:
        st.markdown(f"### รายชื่อปัจจุบัน &nbsp; `{len(st.session_state.students)} คน`")

        if not st.session_state.students:
            st.info("ยังไม่มีรายชื่อนิสิต  \nกรุณานำเข้าจากไฟล์หรือวางรหัสทางซ้าย")
        else:
            # Download current list
            st.download_button(
                "⬇️ ดาวน์โหลดรายชื่อปัจจุบัน",
                data="\n".join(st.session_state.students),
                file_name="students.txt",
                mime="text/plain",
            )

            st.markdown("<br>", unsafe_allow_html=True)

            # Table with current data
            rows = []
            for sid in st.session_state.students:
                d  = st.session_state.data.get(sid, {})
                cy = cohort_year(sid)
                ye = years_enrolled(sid)
                sc = progress_score(sid)
                rows.append({
                    "รหัสนิสิต":    sid,
                    "รุ่น (BE)":   cy or "?",
                    "ปีที่ศึกษา":  ye if cy else "?",
                    "ชื่อ-สกุล":   d.get("name_th") or d.get("name_en") or "—",
                    "คืบหน้า":     f"{sc}/7" if sc >= 0 else "ยังไม่ดึง",
                })

            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "รุ่น (BE)": st.column_config.NumberColumn(format="%d"),
                    "ปีที่ศึกษา": st.column_config.NumberColumn(format="ปีที่ %d"),
                }
            )

            # Clear button
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ ล้างรายชื่อทั้งหมด", type="secondary"):
                st.session_state.students = []
                st.session_state.data = {}
                st.rerun()


# ══════════════════════════════════════════════════════════════════
# TAB 2 — DASHBOARD GRID
# ══════════════════════════════════════════════════════════════════

with tab_dashboard:
    if not st.session_state.students:
        st.info("กรุณาเพิ่มรายชื่อนิสิตใน Tab 'จัดการรายชื่อนิสิต' ก่อน")
        st.stop()

    # Quick refresh in this tab
    col_h1, col_h2 = st.columns([5, 1])
    with col_h1:
        st.markdown("## Dashboard ความคืบหน้านิสิต")
        if st.session_state.last_updated:
            st.caption(f"ข้อมูลล่าสุด: {st.session_state.last_updated}")
    with col_h2:
        if st.button("🔄 Refresh", use_container_width=True):
            do_fetch(st.session_state.students)
            st.rerun()

    fetched = {sid: st.session_state.data[sid] for sid in st.session_state.students if sid in st.session_state.data}

    if not fetched:
        st.warning("ยังไม่มีข้อมูล — กด **🔄 ดึงข้อมูลทั้งหมด** ในแถบด้านซ้าย")
        st.stop()

    # ── Summary row ──
    all_scores   = [progress_score(sid) for sid in st.session_state.students if sid in st.session_state.data]
    total_ms     = len(st.session_state.students) * len(tr.MILESTONES)
    total_done   = sum(all_scores)
    total_revise = sum(
        1 for sid in st.session_state.students
        for m in st.session_state.data.get(sid, {}).get("milestones", [])
        if m["status"] == "revise"
    )
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("นิสิตทั้งหมด",         len(st.session_state.students))
    c2.metric("คะแนนเฉลี่ย",          f"{avg_score:.1f} / 7")
    c3.metric("Milestones ผ่านแล้ว",  f"{total_done} / {total_ms}")
    c4.metric("รายการที่ต้องแก้ไข ⚠️", total_revise)

    st.divider()

    # ── Legend ──
    st.markdown(
        " &nbsp;&nbsp; ".join(
            f"{STATUS_ICON[k]} {STATUS_LABEL[k]}"
            for k in ["approved", "revise", "cancelled", "inprogress", "none"]
        ),
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Year filter ──
    all_years = sorted({cohort_year(sid) for sid in st.session_state.students if cohort_year(sid)})
    sel_years = st.multiselect(
        "กรองตามรุ่น",
        options=all_years,
        default=all_years,
        format_func=lambda y: f"รุ่น {str(y)[2:]} (BE {y})",
        label_visibility="collapsed",
    )

    # ── Grid table ──
    header_cols = ["นิสิต", "รุ่น", "ปีที่"] + MS_SHORTS + ["คะแนน"]
    rows_html = ""

    for sid in st.session_state.students:
        if cohort_year(sid) not in sel_years:
            continue
        d  = st.session_state.data.get(sid, {})
        if not d:
            continue

        cy   = cohort_year(sid)
        ye   = years_enrolled(sid)
        name = d.get("name_en") or sid
        if d.get("name_th"):
            name += f"<br><small style='color:#64748b'>{d['name_th']}</small>"
        name += f"<br><small class='mono' style='color:#475569'>{sid}</small>"

        ms_html = ""
        sc = 0
        for m in d.get("milestones", []):
            icon     = STATUS_ICON.get(m["status"], "?")
            tip_text = m["label"]
            if m.get("latest"):
                tip_text += f": {m['latest']['result'][:60]}"
            if m.get("history"):
                tip_text += f" (+{len(m['history'])} ครั้งก่อน)"
            ms_html += f'<td style="text-align:center" title="{tip_text}">{icon}</td>'
            if m["status"] == "approved":
                sc += 1

        year_badge = f'<span class="year-badge">BE {cy}</span>'
        rows_html += (
            f"<tr>"
            f"<td>{name}</td>"
            f"<td>{year_badge}</td>"
            f"<td style='text-align:center'>ปีที่ {ye}</td>"
            f"{ms_html}"
            f"<td style='text-align:center;font-weight:700;color:{'#10b981' if sc >= 5 else '#f59e0b' if sc >= 2 else '#ef4444'}'>{sc}/7</td>"
            f"</tr>"
        )

    header_html = "".join(f"<th>{h}</th>" for h in header_cols)
    table_html = f"""
    <style>
    .wrts-table {{ width:100%; border-collapse:collapse; font-size:0.83rem; }}
    .wrts-table th {{
        background:#1e2333; padding:8px 10px; text-align:left;
        color:#94a3b8; font-size:0.7rem; text-transform:uppercase;
        letter-spacing:0.05em; border-bottom:1px solid #2a3045;
        white-space:nowrap;
    }}
    .wrts-table td {{ padding:10px 10px; border-bottom:1px solid #1e2333; vertical-align:middle; }}
    .wrts-table tr:hover td {{ background:#1e2333; }}
    </style>
    <div style="overflow-x:auto; border:1px solid #2a3045; border-radius:10px;">
    <table class="wrts-table">
      <thead><tr>{header_html}</tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# TAB 3 — ANALYTICS BY COHORT
# ══════════════════════════════════════════════════════════════════

with tab_analytics:
    st.markdown("## วิเคราะห์ความคืบหน้าตามรุ่น")

    df = build_df()
    fetched_df = df[df["fetched"] & ~df["error"]] if not df.empty else pd.DataFrame()

    if fetched_df.empty:
        st.info("กด **🔄 ดึงข้อมูลทั้งหมด** ในแถบด้านซ้ายก่อน")
        st.stop()

    # ── Year filter ──
    years_available = sorted(fetched_df["cohort_be"].unique())
    sel_be = st.multiselect(
        "เลือกรุ่นที่ต้องการวิเคราะห์",
        options=years_available,
        default=years_available,
        format_func=lambda y: f"รุ่น {str(y)[2:]} (BE {y}  —  ปีที่ {CURRENT_BE - y + 1})",
    )

    if not sel_be:
        st.warning("กรุณาเลือกอย่างน้อย 1 รุ่น")
        st.stop()

    dff = fetched_df[fetched_df["cohort_be"].isin(sel_be)].copy()

    # Compute cohort median & behind flag
    dff["cohort_median"] = dff.groupby("cohort_be")["score"].transform("median")
    dff["cohort_mean"]   = dff.groupby("cohort_be")["score"].transform("mean")
    dff["behind"]        = dff["score"] < dff["cohort_median"]
    dff["gap"]           = dff["cohort_median"] - dff["score"]

    # ── Summary metrics ──
    n_students  = len(dff)
    n_cohorts   = dff["cohort_be"].nunique()
    overall_avg = dff["score"].mean()
    n_behind    = dff["behind"].sum()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("นิสิตที่วิเคราะห์",    n_students)
    m2.metric("จำนวนรุ่น",             n_cohorts)
    m3.metric("คะแนนเฉลี่ยรวม",        f"{overall_avg:.1f} / 7")
    m4.metric("ต้องให้ความสนใจ ⚠️",    n_behind)

    st.divider()

    # ─────────────────────────────────────────────────────────────
    # CHART 1: Average score by cohort (bar)
    # ─────────────────────────────────────────────────────────────
    st.markdown("### 📊 คะแนนเฉลี่ยตามรุ่น")

    cohort_agg = (
        dff.groupby(["cohort_be", "cohort_label"])
        .agg(mean=("score", "mean"), median=("score", "median"), n=("score", "count"))
        .reset_index()
        .sort_values("cohort_be")
    )

    fig_bar = go.Figure()
    fig_bar.add_bar(
        x=cohort_agg["cohort_label"],
        y=cohort_agg["mean"].round(2),
        name="ค่าเฉลี่ย",
        marker_color="#10b981",
        text=cohort_agg["mean"].round(1),
        textposition="outside",
        textfont=dict(size=12),
    )
    fig_bar.add_scatter(
        x=cohort_agg["cohort_label"],
        y=cohort_agg["median"],
        name="ค่ากลาง (median)",
        mode="markers+lines",
        marker=dict(size=10, color="#f59e0b"),
        line=dict(dash="dot", color="#f59e0b", width=2),
    )
    fig_bar.add_shape(
        type="line", x0=-0.5, x1=len(cohort_agg)-0.5, y0=overall_avg, y1=overall_avg,
        line=dict(color="#64748b", width=1.5, dash="dash"),
    )
    fig_bar.add_annotation(
        x=len(cohort_agg)-0.5, y=overall_avg,
        text=f"ค่าเฉลี่ยรวม {overall_avg:.1f}",
        showarrow=False, xanchor="right",
        font=dict(color="#94a3b8", size=11),
        yshift=10,
    )
    fig_bar.update_layout(
        yaxis=dict(range=[0, 8], dtick=1, title="Milestones ที่ผ่าน", gridcolor="#1e2333"),
        xaxis_title="",
        plot_bgcolor="#0f1117",
        paper_bgcolor="#0f1117",
        font=dict(color="#e2e8f0", family="Sarabun"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(t=30, b=10, l=10, r=10),
        height=350,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # ─────────────────────────────────────────────────────────────
    # CHART 2: Milestone heatmap by cohort
    # ─────────────────────────────────────────────────────────────
    st.markdown("### 🗺️ อัตราการผ่าน Milestone แต่ละขั้น (ตามรุ่น)")

    heat_z, heat_text, y_labels = [], [], []
    for be in sorted(sel_be):
        grp = dff[dff["cohort_be"] == be]
        label = f"รุ่น {str(be)[2:]}"
        y_labels.append(label)
        row_pct, row_txt = [], []
        for i in range(len(tr.MILESTONES)):
            col = f"ms_{i}"
            pct = (grp[col] == "approved").mean() * 100 if col in grp.columns else 0
            row_pct.append(round(pct, 1))
            row_txt.append(f"{pct:.0f}%")
        heat_z.append(row_pct)
        heat_text.append(row_txt)

    fig_heat = go.Figure(go.Heatmap(
        z=heat_z,
        x=MS_LABELS,
        y=y_labels,
        text=heat_text,
        texttemplate="%{text}",
        textfont=dict(size=12, family="IBM Plex Mono"),
        colorscale=[[0, "#0f1117"], [0.4, "#1a4a2e"], [0.7, "#1a6b3a"], [1, "#10b981"]],
        zmin=0, zmax=100,
        colorbar=dict(title="% ผ่าน", ticksuffix="%"),
    ))
    fig_heat.update_layout(
        xaxis=dict(tickangle=-35, side="bottom"),
        plot_bgcolor="#0f1117",
        paper_bgcolor="#0f1117",
        font=dict(color="#e2e8f0", family="Sarabun"),
        margin=dict(t=10, b=100, l=10, r=10),
        height=max(280, len(sel_be) * 70 + 100),
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # ─────────────────────────────────────────────────────────────
    # CHART 3: Individual scatter (strip plot)
    # ─────────────────────────────────────────────────────────────
    st.markdown("### 📍 ความคืบหน้ารายคน")

    dff["สถานะ"] = dff["behind"].map({True: "⚠️ ต่ำกว่าค่ากลาง", False: "✅ ปกติ/สูงกว่าค่ากลาง"})

    fig_strip = px.strip(
        dff,
        x="cohort_label",
        y="score",
        color="สถานะ",
        color_discrete_map={
            "⚠️ ต่ำกว่าค่ากลาง":       "#ef4444",
            "✅ ปกติ/สูงกว่าค่ากลาง":   "#10b981",
        },
        hover_data={"student_id": True, "name_th": True, "name_en": True,
                    "cohort_label": False, "score": True, "years_in": True},
        labels={"cohort_label": "รุ่น", "score": "Milestones ที่ผ่าน"},
        stripmode="overlay",
    )
    # Add median markers per cohort
    for _, row in cohort_agg.iterrows():
        fig_strip.add_shape(
            type="line",
            x0=row["cohort_label"], x1=row["cohort_label"],
            y0=row["median"] - 0.15, y1=row["median"] + 0.15,
            line=dict(color="#f59e0b", width=20),
            opacity=0.5,
        )

    fig_strip.update_traces(marker=dict(size=12, opacity=0.85))
    fig_strip.update_layout(
        yaxis=dict(range=[-0.5, 7.5], dtick=1, gridcolor="#1e2333", title="Milestones ที่ผ่าน"),
        plot_bgcolor="#0f1117",
        paper_bgcolor="#0f1117",
        font=dict(color="#e2e8f0", family="Sarabun"),
        legend=dict(title="", orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=30, b=10, l=10, r=10),
        height=400,
    )
    st.caption("เส้นสีส้มแต่ละรุ่น = ค่ากลาง (median) ของรุ่นนั้น")
    st.plotly_chart(fig_strip, use_container_width=True)

    # ─────────────────────────────────────────────────────────────
    # TABLE: Students below median (need attention)
    # ─────────────────────────────────────────────────────────────
    st.markdown("### ⚠️ นิสิตที่ต้องให้ความสนใจ (ต่ำกว่าค่ากลางของรุ่น)")

    behind_df = dff[dff["behind"]].sort_values(["cohort_be", "gap"], ascending=[True, False])

    if behind_df.empty:
        st.success("🎉 ทุกคนอยู่ที่ค่ากลางหรือสูงกว่า!")
    else:
        # Build display with milestone details
        disp_rows = []
        for _, r in behind_df.iterrows():
            d   = st.session_state.data.get(r["student_id"], {})
            mss = d.get("milestones", [])
            latest_passed = next(
                (m["label"] for m in reversed(mss) if m["status"] == "approved"),
                "ยังไม่มี"
            )
            next_pending = next(
                (m["label"] for m in mss if m["status"] != "approved"),
                "ครบทุก milestone"
            )
            disp_rows.append({
                "รหัสนิสิต":       r["student_id"],
                "รุ่น (BE)":      r["cohort_be"],
                "ปีที่ศึกษา":     f"ปีที่ {r['years_in']}",
                "ชื่อ":           r["name_th"] or r["name_en"] or "—",
                "คะแนน":         f"{int(r['score'])}/7",
                "ค่ากลางรุ่น":   f"{r['cohort_median']:.1f}",
                "ห่างจากค่ากลาง": f"-{r['gap']:.1f}",
                "ผ่านล่าสุด":     latest_passed,
                "ขั้นตอนถัดไป":   next_pending,
            })

        st.dataframe(
            pd.DataFrame(disp_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "ห่างจากค่ากลาง": st.column_config.TextColumn(help="คะแนนที่ต่ำกว่าค่ากลางของรุ่น"),
            }
        )

        # Download the list
        behind_csv = pd.DataFrame(disp_rows).to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Export รายชื่อนิสิตที่ต้องติดตาม (.csv)",
            data=behind_csv,
            file_name=f"wrts_behind_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

    # ─────────────────────────────────────────────────────────────
    # TABLE: Cohort summary
    # ─────────────────────────────────────────────────────────────
    st.markdown("### 📋 สรุปตามรุ่น")

    summary_rows = []
    for be in sorted(sel_be):
        grp    = dff[dff["cohort_be"] == be]
        behind = grp["behind"].sum()
        summary_rows.append({
            "รุ่น (BE)":        be,
            "ปีที่ศึกษา":      f"ปีที่ {CURRENT_BE - be + 1}",
            "จำนวนนิสิต":      len(grp),
            "คะแนนเฉลี่ย":    round(grp["score"].mean(), 2),
            "ค่ากลาง":         grp["score"].median(),
            "คะแนนสูงสุด":    int(grp["score"].max()),
            "คะแนนต่ำสุด":    int(grp["score"].min()),
            "ต้องติดตาม":      int(behind),
            "% ต้องติดตาม":   f"{behind/len(grp)*100:.0f}%",
        })

    st.dataframe(
        pd.DataFrame(summary_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "รุ่น (BE)": st.column_config.NumberColumn(format="%d"),
        }
    )
