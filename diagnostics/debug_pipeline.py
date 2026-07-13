import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

from scrapers.greenhouse import GreenhouseScraper
from scrapers.custom.freshworks import FreshworksScraper
from scrapers.custom.datametica import DatameticaScraper
from pipeline.normalizer import normalise
from pipeline.location_filter import filter_jobs as loc_filter
from pipeline.role_filter import matches_role_whitelist, filter_jobs as role_filter

# Scrape known-working sources
print("Scraping Postman...")
postman_jobs = GreenhouseScraper("Postman", "postman").fetch()
print(f"  Postman: {len(postman_jobs)} raw")

print("Scraping Freshworks...")
fw_jobs = FreshworksScraper().fetch()
print(f"  Freshworks: {len(fw_jobs)} raw")

print("Scraping Datametica...")
dm_jobs = DatameticaScraper().fetch()
print(f"  Datametica: {len(dm_jobs)} raw")

all_raw = postman_jobs + fw_jobs + dm_jobs
normalised = [normalise(j) for j in all_raw]
loc_passed = loc_filter(normalised)
role_passed = role_filter(loc_passed)

print()
print(f"Total raw: {len(normalised)}")
print(f"After location filter: {len(loc_passed)}")
print(f"After role filter: {len(role_passed)}")

print()
print("=== LOCATION MATCHED JOBS ===")
for j in loc_passed:
    rm = matches_role_whitelist(j["title"])
    flag = "[ROLE]" if rm else "     "
    print(f"{flag} {j['company']} | {j['title']} | {j['location']}")

print()
print("=== ROLE FILTER KEYWORD TEST ===")
tests = [
    ("Data Scientist", True),
    ("Machine Learning Engineer", True),
    ("LLM Engineer", True),
    ("AI Research Scientist", True),
    ("Data Analyst", True),
    ("Senior Software Engineer", False),
    ("Product Manager", False),
    ("Data Entry Analyst", False),
    ("AI Product Manager", False),
]
all_ok = True
for title, expected in tests:
    got = matches_role_whitelist(title)
    ok = got == expected
    if not ok:
        all_ok = False
    print(f"  {'OK' if ok else 'FAIL'} [{title}] expected={expected} got={got}")

print()
print(f"Role filter correctness: {'ALL CORRECT' if all_ok else 'ERRORS FOUND!'}")
