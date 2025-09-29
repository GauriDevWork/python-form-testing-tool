import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright
import os
import uuid

app = FastAPI(title="Form Tester (Dev)")

# Ensure artifacts dir exists and serve it
ARTIFACT_DIR = os.path.join(os.getcwd(), "artifacts")
os.makedirs(ARTIFACT_DIR, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=ARTIFACT_DIR), name="artifacts")

@app.get("/")
def read_root():
    return {"message": "Form Testing Tool backend is running"}

@app.get("/screenshot")
def screenshot(url: str = Query(..., description="URL to screenshot")):
    """Takes a screenshot of the given URL and returns the artifact path (relative)."""
    # basic validation
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="url must start with http:// or https://")

    job_id = uuid.uuid4().hex[:8]
    filename = f"{job_id}.png"
    full_path = os.path.join(ARTIFACT_DIR, filename)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.screenshot(path=full_path, full_page=True)
            browser.close()
    except Exception as e:
        # return a helpful message for debugging
        raise HTTPException(status_code=500, detail=f"Playwright error: {e}")

    # return a JSON with the public URL to the artifact
    artifact_url = f"/artifacts/{filename}"
    return JSONResponse({"status": "ok", "screenshot": artifact_url})
