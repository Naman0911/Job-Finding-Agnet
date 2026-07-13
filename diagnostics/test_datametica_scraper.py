import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup
from scrapers.custom.datametica import DatameticaScraper

def main():
    scraper = DatameticaScraper()
    print("Fetching jobs via DatameticaScraper...")
    jobs = scraper.fetch()
    print(f"Scraper returned {len(jobs)} jobs:")
    for i, j in enumerate(jobs):
        print(f"  {i+1}. Title: {j.title!r}")
        print(f"     Location: {j.location!r}")
        print(f"     URL: {j.url!r}")

if __name__ == "__main__":
    main()
