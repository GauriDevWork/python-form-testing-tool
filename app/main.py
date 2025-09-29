import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from playwright.sync_api import sync_playwright
import os, uuid, json, datetime

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

