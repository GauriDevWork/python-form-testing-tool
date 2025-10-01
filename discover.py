# discover.py
import sys, json
from playwright.sync_api import sync_playwright, TimeoutError

def make_form_selector(form_elem, index):
    fid = form_elem.get_attribute("id") or ""
    fclass = form_elem.get_attribute("class") or ""
    if fid:
        return f"form#{fid}"
    if fclass:
        cls = fclass.split()[0]
        return f"form.{cls}"
    return f"form:nth-of-type({index+1})"

def extract_label_text(page, inp):
    # try label[for=id], then ancestor label
    id_ = inp.get_attribute("id") or ""
    label_text = ""
    if id_:
        lab = page.query_selector(f"label[for='{id_}']")
        if lab:
            label_text = lab.inner_text().strip()
    if not label_text:
        try:
            parent_label = inp.query_selector("xpath=ancestor::label[1]")
            if parent_label:
                label_text = parent_label.inner_text().strip()
        except Exception:
            pass
    return label_text

def discover_forms(url, timeout=30000):
    results = {"url": url, "forms": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)

        forms = page.query_selector_all("form")
        for i, f in enumerate(forms):
            try:
                action = f.get_attribute("action") or ""
                method = (f.get_attribute("method") or "get").lower()
                fid = f.get_attribute("id") or ""
                fclass = f.get_attribute("class") or ""
                selector = make_form_selector(f, i)
                visible = f.is_visible()

                # short preview HTML (first 300 chars)
                preview = f.inner_html()[:300].strip()

                # gather fields
                fields = []
                inputs = f.query_selector_all("input, textarea, select")
                for inp in inputs:
                    try:
                        tag = inp.evaluate("e => e.tagName.toLowerCase()")
                        typ = (inp.get_attribute("type") or "").lower()
                        name = inp.get_attribute("name") or ""
                        id_ = inp.get_attribute("id") or ""
                        placeholder = inp.get_attribute("placeholder") or ""
                        classes = inp.get_attribute("class") or ""
                        aria = inp.get_attribute("aria-label") or inp.get_attribute("title") or ""
                        label = extract_label_text(page, inp)

                        # build a field selector scoped to the form
                        if name:
                            field_selector = f"{selector} [name='{name}']"
                        elif id_:
                            field_selector = f"#{id_}"
                        else:
                            # fallback: tag + class
                            field_selector = f"{tag}{('.' + classes.split()[0]) if classes else ''}"

                        fields.append({
                            "tag": tag,
                            "type": typ or ("textarea" if tag=="textarea" else ""),
                            "name": name,
                            "id": id_,
                            "placeholder": placeholder,
                            "label": label,
                            "classes": classes,
                            "aria": aria,
                            "selector": field_selector,
                            "visible": inp.is_visible()
                        })
                    except Exception:
                        continue

                results["forms"].append({
                    "form_index": i,
                    "selector": selector,
                    "action": action,
                    "method": method,
                    "visible": visible,
                    "preview_html": preview,
                    "fields": fields
                })
            except Exception as e:
                results["forms"].append({"form_index": i, "error": str(e)})
        browser.close()
    return results

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python discover.py <url>")
        sys.exit(1)
    url = sys.argv[1]
    try:
        r = discover_forms(url)
        print(json.dumps(r, indent=2))
    except TimeoutError as te:
        print("Timeout while loading page:", te)
    except Exception as e:
        print("Error:", e)
