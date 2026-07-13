import sys
from playwright.sync_api import sync_playwright

def main():
    url = "https://onixnet.darwinbox.in/ms/candidatev2/main/careers/allJobs"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        print("Navigating to page...")
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(5000)
            html = page.content()
            with open("diagnostics/onix_careers.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("Successfully saved page HTML to diagnostics/onix_careers.html")
        except Exception as e:
            print("Error:", e)
        finally:
            browser.close()

if __name__ == "__main__":
    main()
