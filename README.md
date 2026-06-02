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

**First time setup:**
1. Copy `students.txt.example` to `students.txt`
2. Replace example IDs with real student IDs
3. **Keep `students.txt` local only** — it's excluded from Git for privacy

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

---

## 🖥️ Local Service Mode (Auto-Scheduled)

Run the dashboard as a self-maintaining local service on a Windows PC — no manual intervention needed.

### How it works

```
Windows Task Scheduler
  ├── WRTS_FetchWeekly      → runs fetch_data.py every Monday at 06:00
  ├── WRTS_FetchStartup     → runs fetch_data.py 60s after PC boots
  └── WRTS_StreamlitStartup → starts Streamlit 90s after PC boots

fetch_data.py  →  wrts_cache.json  ←  app.py (reads on startup)
```

### Setup (one-time, requires Admin)

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the setup script as Administrator:
   ```powershell
   # 1. Press Win key, type "powershell"
   # 2. Right-click "Windows PowerShell" → "Run as administrator"
   # 3. Paste this command (adjust path if needed):
   powershell.exe -ExecutionPolicy Bypass -File "C:\Users\FengPC\WRTS\WRTS-Progress-Dashboard\setup_tasks.ps1"
   ```
   > **Note:** Double-clicking `.ps1` files opens Notepad — you must run them through PowerShell explicitly as shown above.

   With custom schedule (e.g. Friday at 08:00):
   ```powershell
   powershell.exe -ExecutionPolicy Bypass -File "C:\Users\FengPC\WRTS\WRTS-Progress-Dashboard\setup_tasks.ps1" -WeeklyDay FRI -WeeklyTime "08:00"
   ```

3. Reboot the PC. The dashboard will start automatically.

### Accessing from another PC on the same network

1. On the host PC, find its local IP address:
   ```
   ipconfig
   ```
   Look for **IPv4 Address** under your active network adapter (e.g. `192.168.1.42`).

2. On any other PC on the same network, open a browser and go to:
   ```
   http://192.168.1.42:8501
   ```

### Stopping the services

```powershell
# Open PowerShell (no Admin needed) and run:
powershell.exe -ExecutionPolicy Bypass -File "C:\Users\FengPC\WRTS\WRTS-Progress-Dashboard\stop_services.ps1"
```

### Customising the schedule

```powershell
# Example: fetch every Friday at 08:00, use port 8502
.\setup_tasks.ps1 -WeeklyDay FRI -WeeklyTime "08:00" -Port 8502
```

### Local files created by the service

| File | Description |
|---|---|
| `wrts_cache.json` | Cached student data (written by `fetch_data.py`) |
| `wrts_fetch.log` | Fetch run log (JSON Lines format, rotates at 1 MB) |
| `.fetch.lock` | Temporary lock file (present only during a fetch run) |

---

## ⚠️ PDPA Data Notice

`wrts_cache.json` contains **personal data** (student names and thesis progress).

- **Do NOT** share, upload, or email this file.
- **Do NOT** commit it to any Git repository (it is listed in `.gitignore`).
- **Do NOT** store it on a cloud drive (OneDrive, Google Drive, Dropbox, etc.).
- Keep it on the local PC only, accessible only to authorised staff.

This system is designed for use on a **trusted local network** only.  
It does not transmit student data to any service other than `https://info.grad.ku.ac.th/track/`.
