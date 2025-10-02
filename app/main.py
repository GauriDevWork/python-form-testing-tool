import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Query, HTTPException, Request, Body
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from playwright.sync_api import sync_playwright
from discover import discover_forms
from fastapi.responses import JSONResponse
import os, uuid, json, datetime, urllib.parse


TEMPLATES_DIR = os.path.join(os.getcwd(), "templates_data")
os.makedirs(TEMPLATES_DIR, exist_ok=True)

def hostname_to_filename(hostname: str) -> str:
    safe = "".join(c if c.isalnum() or c in ("-",".") else "_" for c in hostname)
    return f"{safe}_template.json"

def save_template_for_url(url: str, template_data: dict):
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or "site"
    fname = hostname_to_filename(hostname)
    path = os.path.join(TEMPLATES_DIR, fname)
    template_data.setdefault("url", url)
    template_data["hostname"] = hostname
    template_data["saved_at"] = datetime.datetime.utcnow().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(template_data, f, indent=2)
    return path

def load_template_for_url(url: str):
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or "site"
    fname = hostname_to_filename(hostname)
    path = os.path.join(TEMPLATES_DIR, fname)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


app = FastAPI(title="Form Tester (Dev)")

# Directories
ROOT = os.getcwd()
ARTIFACT_DIR = os.path.join(ROOT, "artifacts")
os.makedirs(ARTIFACT_DIR, exist_ok=True)

# Serve artifacts and templates
app.mount("/artifacts", StaticFiles(directory=ARTIFACT_DIR), name="artifacts")
templates = Jinja2Templates(directory=os.path.join("app", "templates"))

JOBS_LOG = os.path.join(ROOT, "jobs.json")

def append_job_log(entry: dict):
    # Append to jobs.json; create if missing
    try:
        if not os.path.exists(JOBS_LOG):
            with open(JOBS_LOG, "w", encoding="utf-8") as f:
                json.dump([entry], f, indent=2)
            return
        with open(JOBS_LOG, "r+", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception:
                data = []
            data.append(entry)
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()
    except Exception as e:
        # best-effort logging; don't crash the endpoint
        print("Failed to write jobs.json:", e)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/ping")
def ping():
    return {"status": "ok", "time": datetime.datetime.utcnow().isoformat()}

@app.get("/screenshot")
def screenshot(
    url: str = Query(..., description="URL to capture (http/https)"),
    full_page: str = Query("true", description="true/false"),
    clip: str = Query(None, description="clip as x,y,width,height (optional)"),
    timeout: int = Query(30000, description="navigation timeout in ms (default 30000)")
):
    """Capture screenshot. Query params:
       - url (required)
       - full_page (true/false)
       - clip (optional) "x,y,width,height"
    """
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="url must start with http:// or https://")

    job_id = uuid.uuid4().hex[:10]
    filename = f"{job_id}.png"
    full_path = os.path.join(ARTIFACT_DIR, filename)
    metadata = {"job_id": job_id, "url": url, "full_page": full_page, "clip": clip, "timeout": timeout}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout)
            # optional clip handling
            if clip:
                try:
                    parts = [int(p) for p in clip.split(",")]
                    if len(parts) == 4:
                        x,y,w,h = parts
                        page.screenshot(path=full_path, clip={"x": x, "y": y, "width": w, "height": h})
                    else:
                        page.screenshot(path=full_path, full_page=(full_page.lower()=="true"))
                except Exception as ex:
                    # fallback to full page on parse error
                    metadata["clip_error"] = str(ex)
                    page.screenshot(path=full_path, full_page=(full_page.lower()=="true"))
            else:
                page.screenshot(path=full_path, full_page=(full_page.lower()=="true"))
            browser.close()
        artifact_url = f"/artifacts/{filename}"
        metadata["artifact"] = artifact_url
        metadata["status"] = "ok"
        metadata["timestamp"] = datetime.datetime.utcnow().isoformat()
        # log job
        append_job_log(metadata)
        return JSONResponse({"status": "ok", "job_id": job_id, "screenshot": artifact_url, "metadata": metadata})
    except Exception as e:
        metadata["status"] = "error"
        metadata["error"] = str(e)
        metadata["timestamp"] = datetime.datetime.utcnow().isoformat()
        append_job_log(metadata)
        raise HTTPException(status_code=500, detail=f"Playwright error: {e}")

@app.get("/discover")
def discover_endpoint(url: str):
    if not (url.startswith("http://") or url.startswith("https://")):
        return JSONResponse({"error":"url must start with http/https"}, status_code=400)
    try:
        res = discover_forms(url)
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    

@app.post("/select_template")
def select_template(payload: dict = Body(...)):
    """
    Save a template JSON for a URL.
    Expected payload:
    {
      "url": "https://staging.example.com/contact",
      "form_index": 0,
      "form_selector": "form#wpcf7-f123",
      "mapping": { "your-name": "Test User", "your-email": "test@example.com" }
    }
    """
    url = payload.get("url")
    if not url:
        return JSONResponse({"error":"url required"}, status_code=400)
    try:
        template = {
            "form_index": payload.get("form_index"),
            "form_selector": payload.get("form_selector"),
            "mapping": payload.get("mapping", {})
        }
        path = save_template_for_url(url, template)
        return JSONResponse({"status":"ok", "path": path})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)



# Add the endpoint (paste after other routes)
@app.get("/run_template")
def run_template(url: str):
    """
    Run a saved template for the given URL.
    Returns JSON:
    {
      "result": "PASS"|"FAIL",
      "job_log": [...],
      "screenshot": "/artifacts/<file>"
    }
    """
    template = load_template_for_url(url)
    if not template:
        return JSONResponse({"error": "No template found for this URL. Save one first."}, status_code=404)

    form_selector = template.get("form_selector")
    form_index = template.get("form_index", 0)
    mapping = template.get("mapping", {})

    job_log = []
    artifact_url = None
    success = False

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            job_log.append({"action":"goto", "status":"ok"})

            # find form
            form = None
            if form_selector:
                try:
                    form = page.query_selector(form_selector)
                    job_log.append({"action":"find_form_selector", "selector": form_selector, "found": bool(form)})
                except Exception as e:
                    job_log.append({"action":"find_form_selector", "selector": form_selector, "error": str(e)})
            if not form:
                forms = page.query_selector_all("form")
                job_log.append({"action":"forms_count", "count": len(forms)})
                if len(forms) > form_index:
                    form = forms[form_index]
                    job_log.append({"action":"find_form_by_index", "index": form_index, "found": True})
                else:
                    job_log.append({"action":"find_form_by_index", "index": form_index, "found": False})

            if not form:
                browser.close()
                return JSONResponse({"error":"Form not found on page", "job_log": job_log}, status_code=404)

            # fill fields (scoped to the form where possible)
            for name, val in mapping.items():
                try:
                    field = form.query_selector(f"[name='{name}']")
                    if field:
                        field.fill(val)
                        job_log.append({"action":"fill","field":name,"status":"ok","note":"form-scoped"})
                    else:
                        # fallback: page-level selector
                        sel = f"[name='{name}']"
                        page.fill(sel, val)
                        job_log.append({"action":"fill","field":name,"status":"ok","note":"page-level fallback"})
                except Exception as e:
                    job_log.append({"action":"fill","field":name,"status":"error","error": str(e)})

            # submit
            try:
                btn = form.query_selector("button[type='submit'], input[type='submit'], button:not([type])")
                if btn:
                    btn.click()
                    job_log.append({"action":"click_submit","status":"ok"})
                else:
                    # fallback to form.submit()
                    try:
                        page.evaluate("(f) => f.submit()", form)
                        job_log.append({"action":"form_submit","status":"ok","note":"used form.submit()"})
                    except Exception as e:
                        job_log.append({"action":"form_submit","status":"error","error": str(e)})
            except Exception as e:
                job_log.append({"action":"submit","status":"error","error": str(e)})

            # wait for response / success indicator (try CF7 common selectors)
            page.wait_for_timeout(3000)  # small wait for server response
            # check CF7 success class
            cf7_ok = page.query_selector(".wpcf7-mail-sent-ok")
            if cf7_ok:
                success = True
                job_log.append({"action":"detect_cf7_ok","status":"ok","found":True})
            else:
                # check for general response output text
                resp_out = page.query_selector(".wpcf7-response-output")
                if resp_out and resp_out.inner_text().strip():
                    job_log.append({"action":"response_output","text": resp_out.inner_text().strip()[:200]})
                job_log.append({"action":"detect_cf7_ok","status":"ok","found":False})

            # take a screenshot after submit
            out_file = f"{uuid.uuid4().hex[:10]}_submit.png"
            out_path = os.path.join(ARTIFACT_DIR, out_file)
            try:
                page.screenshot(path=out_path, full_page=True)
                artifact_url = f"/artifacts/{out_file}"
                job_log.append({"action":"screenshot","path": artifact_url, "status":"ok"})
            except Exception as e:
                job_log.append({"action":"screenshot","status":"error","error": str(e)})

            browser.close()

        return JSONResponse({
            "result": "PASS" if success else "FAIL",
            "job_log": job_log,
            "screenshot": artifact_url
        })
    except Exception as e:
        job_log.append({"action":"exception","error": str(e)})
        return JSONResponse({"error": str(e), "job_log": job_log}, status_code=500)