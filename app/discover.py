# app/discover.py
import os, time, traceback
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

HEADFUL = os.environ.get("PLAYWRIGHT_HEADFUL", "0") == "1"

def _safe_text(el):
    try:
        return el.inner_text().strip()
    except Exception:
        return ""

def _inspect_frame(frame):
    out = []
    try:
        forms = frame.query_selector_all("form")
        for i, fh in enumerate(forms):
            try:
                visible = True
                try:
                    visible = fh.is_visible()
                except:
                    visible = True
                preview_html = ""
                try:
                    preview_html = fh.inner_html()
                except:
                    preview_html = ""
                selector = f"form:nth-of-type({i+1})"
                fields = []
                inputs = fh.query_selector_all("input,textarea,select")
                for inp in inputs:
                    try:
                        name = inp.get_attribute("name") or inp.get_attribute("id") or ""
                        id_ = inp.get_attribute("id") or ""
                        typ = inp.get_attribute("type") or ""
                        tag = inp.evaluate("el => el.tagName.toLowerCase()")
                        if not typ:
                            typ = "textarea" if tag == "textarea" else "select" if tag == "select" else "text"
                        placeholder = inp.get_attribute("placeholder") or ""
                        label = ""
                        if id_:
                            lab = frame.query_selector(f"label[for='{id_}']")
                            if lab:
                                label = _safe_text(lab)
                        fields.append({"name": name, "id": id_, "type": typ.lower(), "label": label, "placeholder": placeholder})
                    except Exception:
                        continue
                out.append({"form_index": i, "selector": selector, "visible": visible, "preview_html": preview_html, "fields": fields, "in_iframe": True})
            except Exception:
                continue
    except Exception:
        pass
    return out

def discover_forms(url: str, timeout_ms: int = 60000):
    print("discover_forms: starting for", url)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not HEADFUL, args=["--no-sandbox"] if os.name != "nt" else [])
            page = browser.new_page()
            page.set_viewport_size({"width": 1280, "height": 900})
            page.set_extra_http_headers({"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FormTester/1.0"})
            try:
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except PWTimeout as e:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                except Exception as e2:
                    browser.close()
                    raise Exception(f"Navigation failed: {e2}")

            time.sleep(1.2)

            forms_out = []

            try:
                form_handles = page.query_selector_all("form")
                for i, fh in enumerate(form_handles):
                    try:
                        visible = True
                        try:
                            visible = fh.is_visible()
                        except:
                            visible = True
                        preview_html = ""
                        try:
                            preview_html = fh.inner_html()
                        except:
                            preview_html = ""
                        selector = f"form:nth-of-type({i+1})"
                        fields = []
                        inputs = fh.query_selector_all("input,textarea,select")
                        for inp in inputs:
                            try:
                                name = inp.get_attribute("name") or inp.get_attribute("id") or ""
                                id_ = inp.get_attribute("id") or ""
                                typ = inp.get_attribute("type") or ""
                                tag = inp.evaluate("el => el.tagName.toLowerCase()")
                                if not typ:
                                    typ = "textarea" if tag == "textarea" else "select" if tag == "select" else "text"
                                placeholder = inp.get_attribute("placeholder") or ""
                                label = ""
                                if id_:
                                    lab = page.query_selector(f"label[for='{id_}']")
                                    if lab:
                                        label = _safe_text(lab)
                                fields.append({"name": name, "id": id_, "type": typ.lower(), "label": label, "placeholder": placeholder})
                            except Exception:
                                continue
                        forms_out.append({"form_index": i, "selector": selector, "visible": visible, "preview_html": preview_html, "fields": fields, "in_iframe": False})
                    except Exception as e:
                        print("Error reading top-level form:", e)
            except Exception as e:
                print("No top-level forms enumerated:", e)

            try:
                frames = page.frames
                if len(frames) > 1:
                    for fr in frames:
                        if fr == page.main_frame:
                            continue
                        try:
                            fforms = fr.query_selector_all("form")
                            if fforms:
                                iframe_forms = _inspect_frame(fr)
                                if iframe_forms:
                                    base = len(forms_out)
                                    for idx, ff in enumerate(iframe_forms):
                                        ff["form_index"] = base + idx
                                        forms_out.append(ff)
                        except Exception as e:
                            print("Iframe access error (may be cross-origin), skipping:", e)
            except Exception as e:
                print("Frames enumeration error:", e)

            browser.close()
            print("discover_forms: finished, total forms:", len(forms_out))
            return {"forms": forms_out}
    except Exception as exc:
        tb = traceback.format_exc()
        print("discover_forms: exception:", exc)
        print(tb)
        raise Exception(f"discover error: {exc}")
