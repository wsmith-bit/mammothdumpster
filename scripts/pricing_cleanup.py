from pathlib import Path
import re
import argparse

REPLACEMENT = "For current pricing, refer to mammothdumpster.com or call/text 603-880-8000."

START_MARKER = "<!-- Dumpster Sizes Section -->"
END_MARKER = "<!-- GBP Map Section -->"

EXCLUDE_PARTS = {"node_modules", "dist", "build", ".git"}
MONEY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?")

# Replace full obvious pricing-bearing HTML blocks outside protected section.
BLOCK_RE = re.compile(
    r"(<(?:p|li|td|dd|div|span)[^>]*>)(.*?\$\s?\d[\d,]*(?:\.\d{2})?.*?)(</(?:p|li|td|dd|div|span)>)",
    re.IGNORECASE | re.DOTALL,
)

# JSON-LD answer fields containing dollar values.
JSON_ANSWER_RE = re.compile(
    r'("acceptedAnswer"\s*:\s*\{\s*"@type"\s*:\s*"Answer"\s*,\s*"text"\s*:\s*")([^"]*\$\s?\d[\d,]*(?:\.\d{2})?[^"]*)(")',
    re.IGNORECASE | re.DOTALL,
)

def should_scan(path: Path) -> bool:
    if path.suffix.lower() != ".html":
        return False
    if ".min." in path.name:
        return False
    return not any(part in EXCLUDE_PARTS for part in path.parts)

def split_protected(text: str):
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)

    if start == -1 or end == -1 or end <= start:
        return None

    return text[:start], text[start:end], text[end:]

def clean_segment(segment: str):
    replacements = 0

    def replace_json_answer(match):
        nonlocal replacements
        replacements += 1
        return match.group(1) + REPLACEMENT + match.group(3)

    segment = JSON_ANSWER_RE.sub(replace_json_answer, segment)

    def replace_block(match):
        nonlocal replacements
        full_inner = match.group(2)

        # Avoid replacing broad wrappers that contain large sections.
        if len(full_inner) > 1200:
            return match.group(0)

        replacements += 1
        return match.group(1) + REPLACEMENT + match.group(3)

    segment = BLOCK_RE.sub(replace_block, segment)

    return segment, replacements

def count_money_outside(text: str):
    split = split_protected(text)
    if split:
        before, protected, after = split
        outside = before + after
        protected_count = len(MONEY_RE.findall(protected))
    else:
        outside = text
        protected_count = 0

    return len(MONEY_RE.findall(outside)), protected_count

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    files = [p for p in Path(".").rglob("*.html") if should_scan(p)]

    scanned = 0
    skipped_missing_markers = []
    changed = []
    total_replacements = 0
    examples = []

    for path in files:
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="ignore")
        split = split_protected(text)
        if not split:
            # No protected dumpster card section exists on this page.
            # Safe policy: only clean pages that contain actual dollar amounts.
            # General pricing language without dollar values is left alone.
            if MONEY_RE.search(text):
                new_text, reps = clean_segment(text)

                if reps:
                    changed.append(str(path))
                    total_replacements += reps

                    if len(examples) < 10:
                        examples.append((str(path), reps))

                    if args.apply:
                        path.write_text(new_text, encoding="utf-8")
            else:
                skipped_missing_markers.append(str(path))

            continue
       
        before, protected, after = split

        new_before, rep_before = clean_segment(before)
        new_after, rep_after = clean_segment(after)

        reps = rep_before + rep_after

        if reps:
            new_text = new_before + protected + new_after
            changed.append(str(path))
            total_replacements += reps

            if len(examples) < 10:
                examples.append((str(path), reps))

            if args.apply:
                path.write_text(new_text, encoding="utf-8")

    # Verification pass
    outside_money_after = 0
    protected_money_after = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        outside, protected_count = count_money_outside(text)
        # For dry run, this reflects current files, not proposed output.
        outside_money_after += outside
        protected_money_after += protected_count

    print("MODE:", "APPLY" if args.apply else "DRY RUN")
    print("HTML files scanned:", scanned)
    print("Files skipped missing protected markers:", len(skipped_missing_markers))
    print("Files that would change/changed:", len(changed))
    print("Total replacements would make/made:", total_replacements)

    print("\nExamples:")
    for path, reps in examples:
        print(f"- {path}: {reps} replacements")

    print("\nSkipped missing markers, first 25:")
    for path in skipped_missing_markers[:25]:
        print(f"- {path}")

    print("\nCurrent dollar references outside protected sections:", outside_money_after)
    print("Current dollar references inside protected card sections:", protected_money_after)

if __name__ == "__main__":
    main()
