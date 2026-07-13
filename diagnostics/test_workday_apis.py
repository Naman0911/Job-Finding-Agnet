import requests

headers = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

payload = {"limit": 10, "offset": 0, "searchText": ""}

# Test Fractal endpoints
fractal_urls = [
    "https://fractal.wd1.myworkdayjobs.com/wday/cxs/fractal/Fractal/jobs",
    "https://fractal.wd3.myworkdayjobs.com/wday/cxs/fractal/Fractal/jobs",
    "https://fractal.wd1.myworkdayjobs.com/wday/cxs/fractal/Fractal_Careers/jobs",
    "https://fractal.wd3.myworkdayjobs.com/wday/cxs/fractal/Fractal_Careers/jobs",
]

print("=== TESTING FRACTAL ENDPOINTS ===")
for url in fractal_urls:
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"URL: {url} -> Status: {r.status_code}")
        if r.status_code == 200:
            print(f"  SUCCESS! Found {r.json().get('total', 0)} jobs")
            break
    except Exception as e:
        print(f"URL: {url} -> Error: {e}")

# Test BrowserStack endpoints
browserstack_urls = [
    "https://browserstack.wd1.myworkdayjobs.com/wday/cxs/browserstack/browserstack/jobs",
    "https://browserstack.wd3.myworkdayjobs.com/wday/cxs/browserstack/browserstack/jobs",
    "https://browserstack.wd1.myworkdayjobs.com/wday/cxs/browserstack/Browserstack/jobs",
    "https://browserstack.wd1.myworkdayjobs.com/wday/cxs/browserstack/Careers/jobs",
    "https://browserstack.wd1.myworkdayjobs.com/wday/cxs/browserstack/BrowserStack_Careers/jobs",
]

print("\n=== TESTING BROWSERSTACK ENDPOINTS ===")
for url in browserstack_urls:
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"URL: {url} -> Status: {r.status_code}")
        if r.status_code == 200:
            print(f"  SUCCESS! Found {r.json().get('total', 0)} jobs")
            break
    except Exception as e:
        print(f"URL: {url} -> Error: {e}")
