import requests

headers = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

payload = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}

# Test Fractal on wd3
url_fractal = "https://fractal.wd3.myworkdayjobs.com/wday/cxs/fractal/Fractal/jobs"
print("Testing Fractal on wd3:")
try:
    r = requests.post(url_fractal, json=payload, headers=headers, timeout=10)
    print("Status:", r.status_code)
    print("Response text:", r.text[:500])
except Exception as e:
    print("Error:", e)

# Test BrowserStack on wd1
url_bs = "https://browserstack.wd1.myworkdayjobs.com/wday/cxs/browserstack/browserstack/jobs"
print("\nTesting BrowserStack on wd1:")
try:
    r = requests.post(url_bs, json=payload, headers=headers, timeout=10)
    print("Status:", r.status_code)
    print("Response text:", r.text[:500])
except Exception as e:
    print("Error:", e)
