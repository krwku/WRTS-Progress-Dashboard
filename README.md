# WRTS Progress Dashboard

Web-based dashboard for tracking KU Graduate School student progress.  
**Live data from:** https://info.grad.ku.ac.th/track/

---

## 🚀 Deploy to Streamlit Cloud (Free)

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<your-username>/wrts-dashboard.git
git push -u origin main
```

### 2. Deploy on Streamlit Cloud

1. Go to **https://share.streamlit.io**
2. Sign in with GitHub
3. Click **"New app"**
4. Select your repository and set:
   - **Branch:** `main`
   - **Main file path:** `app.py`
5. Click **"Deploy"**

Your dashboard will be live at:  
`https://<your-app>.streamlit.app`

Anyone with the URL can access it — no login required (unless you add auth).

---

## 📁 File Structure

```
wrts-dashboard/
├── app.py              ← Streamlit app (main file)
├── tracker.py          ← WRTS scraper module
├── students.txt        ← Default student list (commit to update)
├── requirements.txt    ← Python dependencies
├── .streamlit/
│   └── config.toml     ← Dark theme config
└── README.md
```

---

## 👥 Managing Students

### Option A: Edit students.txt and commit (permanent)
```
6514500439
6814500981
6714000123
```
One ID per line. Lines starting with `#` are ignored.

### Option B: Upload via the app UI (session only)
Use the **"📁 จัดการรายชื่อนิสิต"** tab to upload a `.txt` file or paste IDs directly.
Data resets when the browser session ends — use Export/Import to save it.

### Option C: Export / Import cache (across sessions)
After fetching data, use the sidebar **💾 Export** button to save a `.json` file.
Next session, **Import** that file to restore all data without re-fetching.

---

## 📈 Analytics Features

| Feature | Description |
|---|---|
| **Cohort year** | First 2 digits of student ID = BE year (e.g. `65` → BE 2565) |
| **Years enrolled** | Current BE − enrollment BE + 1 |
| **Progress score** | Number of milestones with status อนุมัติ/ผ่าน (0–7) |
| **Behind average** | Students below their cohort's median score |
| **Milestone heatmap** | % of cohort that passed each milestone |
| **Export** | Download "needs attention" list as CSV |

---

## ⚙️ Customizing Milestones

Edit the `MILESTONES` list in `tracker.py`:

```python
MILESTONES = [
    {"label": "แต่งตั้งกรรมการ", "short": "กรรมการ",
     "keywords": ["ขอแต่งตั้งคณะกรรมการประจำตัวนิสิต"]},
    # Add more milestones here...
]
```

- `label` — full name shown in tables
- `short` — abbreviated name shown in dashboard column headers  
- `keywords` — Thai substrings matched against the Topic field (OR logic)

---

## 🔒 Privacy Note

This app fetches **publicly accessible** data from the KU Graduate School WRTS system.  
Student IDs are not stored anywhere — they only exist in Streamlit session state  
or in the `students.txt` file you commit to your own private GitHub repository.

Consider making your GitHub repository **private** if you are tracking real students.

---

## 🔄 Auto-refresh

Streamlit Cloud does not support background schedulers.  
Click **"🔄 ดึงข้อมูลทั้งหมด"** in the sidebar to refresh manually,  
or set up a GitHub Action to refresh and commit the cache periodically (advanced).
