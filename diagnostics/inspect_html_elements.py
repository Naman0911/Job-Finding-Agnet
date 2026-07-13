from bs4 import BeautifulSoup

def main():
    with open("diagnostics/onix_careers_loaded.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    soup = BeautifulSoup(html, "html.parser")
    print("Finding all elements containing 'Security'...")
    for tag in ["h1", "h2", "h3", "h4", "div", "span", "p", "a"]:
        elements = soup.find_all(tag)
        for el in elements:
            text = el.get_text(strip=True)
            if "GCP Security" in text or "GCP Infra" in text:
                # Print tag details
                attrs = el.attrs
                print(f"Tag: <{tag}>, Attrs: {attrs}")
                # Print a snippet of the element's direct content (excluding nested elements if possible, or just raw)
                parent = el.parent
                print(f"  Parent tag: <{parent.name}>, Parent Attrs: {parent.attrs}")
                print(f"  Text: {text[:200]!r}")
                print("-" * 50)

if __name__ == "__main__":
    main()
