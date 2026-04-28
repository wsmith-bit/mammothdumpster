from pathlib import Path
import csv
import re
import argparse

START_MARKER = "<!-- Dumpster Sizes Section -->"
END_MARKER = "<!-- GBP Map Section -->"

EXCLUDE_PARTS = {".git", "node_modules", "dist", "build"}

SERVICE_CARD_RE = re.compile(
    r'(<div\b[^>]*class="[^"]*service-card[^"]*"[^>]*>.*?</div>\s*</div>)',
    re.IGNORECASE | re.DOTALL,
)

H3_RE = re.compile(
    r"<h3[^>]*>\s*(.*?)\s*</h3>",
    re.IGNORECASE | re.DOTALL,
)

PRICE_LINE_RE = re.compile(
    r'(<p[^>]*class="[^"]*text-gray-500[^"]*"[^>]*>)(.*?)(</p>)',
    re.IGNORECASE | re.DOTALL,
)

MONEY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?")

def normalize_html_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("&amp;", "&")
    value = re.sub(r"\s+", " ", value)
    return value.strip()

def should_scan(path: Path) -> bool:
    normalized = str(path).replace("\\", "/")
    return (
        path.suffix.lower() == ".html"
        and ".min." not in path.name
        and not any(part in EXCLUDE_PARTS for part in path.parts)
        and not normalized.startswith("questions/")
    )

def load_prices(csv_path: Path):
    prices = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            size = row["size"].strip()
            price = row["price"].strip()

            if not size or not price:
                continue

            if not price.startswith("$"):
                raise ValueError(f"Price must start with $ for {size}: {price}")

            prices[size] = price

    return prices

def split_protected(text: str):
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)

    if start == -1 or end == -1 or end <= start:
        return None

    return text[:start], text[start:end], text[end:]

def update_card(card_html: str, prices: dict):
    h3_match = H3_RE.search(card_html)

    if not h3_match:
        return card_html, None

    card_size = normalize_html_text(h3_match.group(1))

    if card_size not in prices:
        return card_html, None

    new_price = prices[card_size]
    changed = False
    before_after = None

    def replace_price_line(match):
        nonlocal changed, before_after

        open_tag, inner, close_tag = match.groups()

        if not MONEY_RE.search(inner):
            return match.group(0)

        new_inner = MONEY_RE.sub(new_price, inner, count=1)

        if new_inner != inner:
            changed = True
            before_after = (card_size, inner.strip(), new_inner.strip())

        return open_tag + new_inner + close_tag

    new_card = PRICE_LINE_RE.sub(replace_price_line, card_html, count=1)

    if changed:
        return new_card, before_after

    return card_html, None

def update_protected_section(protected: str, prices: dict):
    total_changes = 0
    examples = []
    replacements_by_size = {size: 0 for size in prices}

    def replace_card(match):
        nonlocal total_changes, examples

        card_html = match.group(1)
        new_card, before_after = update_card(card_html, prices)

        if before_after:
            size, old, new = before_after
            total_changes += 1
            replacements_by_size[size] += 1

            if len(examples) < 20:
                examples.append((size, old, new))

        return new_card

    updated = SERVICE_CARD_RE.sub(replace_card, protected)

    return updated, total_changes, replacements_by_size, examples

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes to files")
    parser.add_argument("--pricing", default="pricing.csv", help="Path to pricing CSV")
    args = parser.parse_args()

    prices = load_prices(Path(args.pricing))

    scanned = 0
    marker_missing = 0
    files_changed = 0
    total_replacements = 0
    total_by_size = {size: 0 for size in prices}
    examples = []

    for path in Path(".").rglob("*.html"):
        if not should_scan(path):
            continue

        scanned += 1
        text = path.read_text(encoding="utf-8", errors="ignore")
        split = split_protected(text)

        if not split:
            marker_missing += 1
            continue

        before, protected, after = split
        new_protected, changes, by_size, file_examples = update_protected_section(protected, prices)

        if changes:
            files_changed += 1
            total_replacements += changes

            for size, count in by_size.items():
                total_by_size[size] += count

            examples.extend(file_examples)

            if args.apply:
                path.write_text(before + new_protected + after, encoding="utf-8")

    print("MODE:", "APPLY" if args.apply else "DRY RUN")
    print("HTML files scanned:", scanned)
    print("Files missing protected card markers:", marker_missing)
    print("Files that would change/changed:", files_changed)
    print("Total card price replacements:", total_replacements)

    print("\nReplacements by size:")
    for size, count in total_by_size.items():
        print(f"- {size}: {count}")

    print("\nExamples:")
    for size, old, new in examples[:20]:
        print(f"\n[{size}]")
        print("OLD:", old)
        print("NEW:", new)

if __name__ == "__main__":
    main()