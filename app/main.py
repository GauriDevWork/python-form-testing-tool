import os
import json
import uuid
import time
import threading
import datetime
import urllib.parse
import smtplib
from email.message import EmailMessage
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from playwright.sync_api import sync_playwright

# Optional DB helper (safe to skip)
try:
    from app.db_utils import save_job_record
except Exception:
    def save_job_record(_): pass

# Windows event loop fix
import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# --- CONFIG ---
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "gaurikaushik2013@gmail.com")
SMTP_PASS = os.getenv("SMTP_PASS", "awawjrohjhyglchm")
NOTIFY_TO = os.getenv("NOTIFY_TO", "gaurikaushik2013@gmail.com")

ROOT = os.getcwd()
ARTIFACT_DIR = os.path.join(ROOT, "artifacts")
TEMPLATES_DIR = os.path.join(ROOT, "templates_data")
REPORTS_DIR = os.path.join(ROOT, "reports")
os.makedirs(ARTIFACT_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

app = FastAPI(title="Form Tester – Final Phase 1")
app.mount("/artifacts", StaticFiles(directory=ARTIFACT_DIR), name="artifacts")
app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")
templates = Jinja2Templates(directory=os.path.join("app", "templates"))

jobs: Dict[str, Dict[str, Any]] = {}


# --- HELPERS ---
def safe_filename(s: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", ".") else "_" for c in s)


def template_path_for_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or "site"
    return os.path.join(TEMPLATES_DIR, f"{safe_filename(hostname)}.json")


def take_screenshot(page, job_id: str, tag: str) -> str:
    fname = f"{job_id}_{tag}.png"
    path = os.path.join(ARTIFACT_DIR, fname)
    page.screenshot(path=path, full_page=True)
    return f"/artifacts/{fname}"


def send_result_email(job: Dict[str, Any]) -> Dict[str, Any]:
    """Send report + screenshots via email"""
    if not (SMTP_USER and SMTP_PASS and NOTIFY_TO):
        print("⚠️ Email skipped: SMTP config missing")
        return {"status": "skipped"}

    recipients = [x.strip() for x in NOTIFY_TO.split(",") if x.strip()]
    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"[Form Tester] {job.get('result')} - {job.get('url')}"
    html = [f"<h2>Form Test Result: <span style='color:{'green' if job.get('result')=='PASS' else 'red'}'>{job.get('result')}</span></h2>"]
    html.append(f"<p><strong>URL:</strong> {job.get('url')}</p>")
    html.append(f"<p><strong>Job ID:</strong> {job.get('job_id')}</p>")
    html.append(f"<p><strong>Elapsed:</strong> {job.get('elapsed',0)}s</p>")
    html.append("<h4>Steps:</h4><ul>")
    for s in job.get("steps", [])[-10:]:
        html.append(f"<li>{s.get('action')} {s.get('field','')} {s.get('status','')}</li>")
    html.append("</ul>")
    if job.get("report"):
        html.append(f"<p><a href='{job.get('report')}'>Open Report</a></p>")
    msg.add_alternative("\n".join(html), subtype="html")

    for art in job.get("artifacts", []):
        if art.lower().endswith(".png"):
            local = os.path.join(ARTIFACT_DIR, os.path.basename(art))
            if os.path.exists(local):
                with open(local, "rb") as fh:
                    msg.add_attachment(fh.read(), maintype="image", subtype="png", filename=os.path.basename(art))

    if job.get("report"):
        rpt_local = os.path.join(REPORTS_DIR, os.path.basename(job["report"]))
        if os.path.exists(rpt_local):
            with open(rpt_local, "rb") as fh:
                msg.add_attachment(fh.read(), maintype="text", subtype="html", filename=os.path.basename(rpt_local))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        print(f"✅ Email sent to {recipients}")
        return {"status": "sent"}
    except Exception as e:
        print("❌ Email send failed:", e)
        return {"status": "error", "error": str(e)}


def save_html_report(job: Dict[str, Any]) -> str:
    job_id = job.get("job_id", uuid.uuid4().hex[:8])
    rpt_name = f"{job_id}_report.html"
    rpt_path = os.path.join(REPORTS_DIR, rpt_name)
    try:
        parts = [
            "<html><head><meta charset='utf-8'><title>Form Report</title>",
            "<style>body{font-family:Arial;padding:18px;background:#f8fafc}.card{background:#fff;border:1px solid #ddd;border-radius:6px;padding:10px;margin-bottom:10px}</style>",
            "</head><body>"
        ]
        parts.append(f"<h1>Form Test — {job.get('result')}</h1>")
        parts.append(f"<div class='card'><b>URL:</b> {job.get('url')}<br><b>Job:</b> {job_id}<br><b>Time:</b> {job.get('timestamp')}</div>")
        parts.append("<h3>Steps</h3><pre>" + json.dumps(job.get("steps", []), indent=2) + "</pre>")
        parts.append("<h3>Screenshots</h3>")
        for a in job.get("artifacts", []):
            parts.append(f"<div class='card'><a href='{a}'>{a}</a><br><img src='{a}' style='max-width:700px;border:1px solid #ccc;'/></div>")
        parts.append("</body></html>")
        with open(rpt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))
        return f"/reports/{rpt_name}"
    except Exception as e:
        print("save_html_report error:", e)
        return ""


# --- MAIN BACKGROUND TEST THREAD ---
def background_test(job_id: str, url: str, form_index: int = 0):
    job = jobs[job_id]
    start_ts = time.time()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()

            # Go to URL
            job["steps"].append({"action": "navigate", "status": "running"})
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            job["steps"].append({"action": "navigate_done", "status": "ok"})
            job["progress"] = 10

            # Screenshot & dump HTML
            try:
                shot = take_screenshot(page, job_id, "nav")
                job["artifacts"].append(shot)
                dump = os.path.join(REPORTS_DIR, f"{job_id}_form_debug.html")
                with open(dump, "w", encoding="utf-8") as f:
                    f.write(page.content())
                job["artifacts"].append(f"/reports/{os.path.basename(dump)}")
            except Exception as e:
                job["steps"].append({"action": "debug_dump_error", "error": str(e)})

            # Retry to find forms
            forms = []
            for attempt in range(5):
                try:
                    forms = page.query_selector_all("form")
                    if forms:
                        break
                    page.wait_for_timeout(1000)
                except Exception:
                    pass
            job["steps"].append({"action": "forms_count", "count": len(forms)})

            if not forms:
                job["steps"].append({"action": "no_forms", "status": "fail"})
                job["result"] = "FAIL"
                job["progress"] = 100
                job["elapsed"] = round(time.time() - start_ts, 2)
                job["report"] = save_html_report(job)
                send_result_email(job)
                return

            form = forms[form_index] if len(forms) > form_index else forms[0]
            job["steps"].append({"action": "form_found", "status": "ok"})
            job["progress"] = 20

            # Enumerate fields
            form_details = page.evaluate("""
                (f)=>Array.from(f.querySelectorAll('input,textarea,select')).map(e=>({
                    name:e.name,id:e.id,placeholder:e.placeholder,type:e.type,value:e.value||''
                }))
            """, form)
            job["steps"].append({"action": "form_details", "fields": form_details})

            # Fill fields
            mapping = {
                "first_name": "Test User",
                "your-name": "Test User",
                "name": "Test User",
                "email": "test@example.com",
                "your-email": "test@example.com",
                "phone": "+1-202-555-0198",
                "message": "Automated message"
            }

            filled = 0
            for fld in form_details:
                fname = fld.get("name")
                if not fname:
                    continue
                value = mapping.get(fname, "Test Value")
                step = {"action": "fill", "field": fname, "value": value}
                try:
                    el = form.query_selector(f"[name='{fname}']")
                    if el:
                        try:
                            el.fill(value, timeout=3000)
                        except Exception:
                            page.evaluate("(e,v)=>{e.value=v; e.dispatchEvent(new Event('input',{bubbles:true}))}", el, value)
                        step["status"] = "ok"
                        filled += 1
                    else:
                        step["status"] = "not_found"
                except Exception as e:
                    step["status"] = "error"
                    step["error"] = str(e)
                job["steps"].append(step)
                job["progress"] = min(60, 20 + int(filled * 3))

            # Screenshot after fill
            try:
                shot2 = take_screenshot(page, job_id, "after_fill")
                job["artifacts"].append(shot2)
            except Exception as e:
                job["steps"].append({"action": "screenshot_after_fill_error", "error": str(e)})

            # Submit
            try:
                btn = form.query_selector("button[type='submit'], input[type='submit'], button:not([type])")
                if btn:
                    btn.click()
                    job["steps"].append({"action": "submit", "status": "clicked"})
                else:
                    page.evaluate("(f)=>f.submit()", form)
                    job["steps"].append({"action": "submit", "status": "manual_submit"})
            except Exception as e:
                job["steps"].append({"action": "submit_error", "error": str(e)})
            job["progress"] = 80

            # Wait and detect success
            page.wait_for_timeout(3000)
            success = False
            try:
                if page.query_selector(".wpcf7-mail-sent-ok, .wpforms-confirmation-container"):
                    success = True
                    job["steps"].append({"action": "detect_success", "status": "ok"})
                else:
                    body = page.inner_text("body").lower()
                    if any(w in body for w in ["thank you", "message sent", "successfully sent"]):
                        success = True
                        job["steps"].append({"action": "detect_text_success", "status": "ok"})
            except Exception as e:
                job["steps"].append({"action": "detect_error", "error": str(e)})

            # Screenshot final
            try:
                shot3 = take_screenshot(page, job_id, "after_submit")
                job["artifacts"].append(shot3)
            except Exception:
                pass

            browser.close()
            job["progress"] = 100
            job["result"] = "PASS" if success else "FAIL"

    except Exception as e:
        job["steps"].append({"action": "exception", "error": str(e)})
        job["result"] = "ERROR"
    finally:
        job["elapsed"] = round(time.time() - start_ts, 2)
        job["timestamp"] = datetime.datetime.utcnow().isoformat()
        try:
            job["report"] = save_html_report(job)
        except Exception:
            job["report"] = None
        try:
            send_result_email(job)
        except Exception as e:
            job["steps"].append({"action": "email_error", "error": str(e)})


# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/run_template_async")
def run_template_async(url: str):
    if not url.startswith(("http://", "https://")):
        return JSONResponse({"error": "Invalid URL"}, status_code=400)
    job_id = uuid.uuid4().hex[:10]
    jobs[job_id] = {
        "job_id": job_id,
        "url": url,
        "progress": 0,
        "steps": [],
        "artifacts": [],
        "result": "RUNNING",
        "start": time.time(),
    }
    threading.Thread(target=background_test, args=(job_id, url), daemon=True).start()
    return {"job_id": job_id}


@app.get("/job_status")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "not found"}, status_code=404)
    elapsed = round(time.time() - job.get("start", time.time()), 2)
    progress = job.get("progress", 0)
    eta = round((elapsed / (progress or 1)) * max(0, 100 - progress), 1)
    return {
        "job_id": job_id,
        "url": job.get("url"),
        "progress": progress,
        "elapsed": elapsed,
        "eta": eta,
        "result": job.get("result"),
        "steps": job.get("steps", []),
        "artifacts": job.get("artifacts", []),
    }
