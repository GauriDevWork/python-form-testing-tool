from playwright.sync_api import sync_playwright
import os

os.makedirs("artifacts", exist_ok=True)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.ashtangaintensivebysuvi.com", wait_until="networkidle", timeout=30000)
        out = os.path.join("artifacts", "ashtangaintensivebysuvi.png")
        page.screenshot(path=out, full_page=True)
        browser.close()
        print(f"Saved screenshot: {out}")

if __name__ == "__main__":
    main()
