from bs4 import BeautifulSoup

def main():
    with open("diagnostics/onix_careers_loaded.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    soup = BeautifulSoup(html, "html.parser")
    tile = soup.find("ui-job-tile")
    if tile:
        print("Prettified HTML of one ui-job-tile:")
        print(tile.prettify()[:2000])
    else:
        print("No ui-job-tile found")

if __name__ == "__main__":
    main()
