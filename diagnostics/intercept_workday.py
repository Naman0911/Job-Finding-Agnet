import json
from playwright.sync_api import sync_playwright

def intercept(url, name):
    print(f"\n=== INTERCEPTING {name} WORKDAY CALLS ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        def handle_request(req):
            print("  [Req URL]:", req.url)
            if "/wday/cxs/" in req.url or "jobs" in req.url:
                print("  [Req Headers]:", json.dumps(dict(req.headers), indent=2))
                if req.post_data:
                    print("  [Req Post Data]:", req.post_data)

        def handle_response(res):
            print(f"  [Res URL]: {res.url} -> Status: {res.status}")

        page.on("request", handle_request)
        page.on("response", handle_response)
        
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print("Error navigating:", e)
        finally:
            browser.close()

if __name__ == "__main__":
    # Test BrowserStack
    intercept("https://browserstack.wd1.myworkdayjobs.com/en-US/browserstack/", "BrowserStack")
    # Test Fractal
    intercept("https://fractal.wd3.myworkdayjobs.com/en-US/Fractal/", "Fractal")
