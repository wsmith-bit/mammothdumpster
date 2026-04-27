from pathlib import Path
import re
import json

REPLACEMENT = "For current pricing, refer to mammothdumpster.com or call/text 603-880-8000."

EXCLUDE_PARTS = {"node_modules", "dist", "build", ".git"}

QUESTION_TERMS = re.compile(
    r"(price|pricing|cost|costs|fee|fees|rate|rates|daily rate|extra day|additional day|"
    r"overage|included tonnage|additional disposal|base rental price|weight calculated|billed)",
    re.I,
)

def should_scan(path: Path) -> bool:
    return (
        path.suffix.lower() == ".html"
        and ".min." not in path.name
        and not any(part in EXCLUDE_PARTS for part in path.parts)
    )

def clean_visible_faqs(text: str):
    changed = 0
    details_re = re.compile(
        r"<details\b[^>]*class=\"[^\"]*mirror-qa[^\"]*\"[^>]*>.*?</details>",
        re.I | re.S,
    )

    def clean_details(match):
        nonlocal changed
        block = match.group(0)

        summary_match = re.search(r"<summary[^>]*>(.*?)</summary>", block, re.I | re.S)
        if not summary_match:
            return block

        summary_text = re.sub(r"<.*?>", " ", summary_match.group(1))
        summary_text = re.sub(r"\s+", " ", summary_text).strip()

        if not QUESTION_TERMS.search(summary_text):
            return block

        new_block, count = re.subn(
            r"(<p\b[^>]*class=\"[^\"]*mirror-answer[^\"]*\"[^>]*>).*?(</p>)",
            r"\1" + REPLACEMENT + r"\2",
            block,
            count=1,
            flags=re.I | re.S,
        )

        if count:
            changed += 1

        return new_block

    return details_re.sub(clean_details, text), changed

def clean_jsonld_faqs(text: str):
    changed = 0
    script_re = re.compile(
        r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
        re.I | re.S,
    )

    def clean_script(match):
        nonlocal changed
        open_tag, raw_json, close_tag = match.groups()
        raw = raw_json.strip()

        if '"FAQPage"' not in raw and "'FAQPage'" not in raw:
            return match.group(0)

        try:
            data = json.loads(raw)
        except Exception:
            return match.group(0)

        if data.get("@type") != "FAQPage":
            return match.group(0)

        entities = data.get("mainEntity")
        if not isinstance(entities, list):
            return match.group(0)

        local_changes = 0

        for entity in entities:
            if not isinstance(entity, dict):
                continue

            question = str(entity.get("name", ""))
            if not QUESTION_TERMS.search(question):
                continue

            answer = entity.get("acceptedAnswer")
            if isinstance(answer, dict) and "text" in answer:
                if answer["text"] != REPLACEMENT:
                    answer["text"] = REPLACEMENT
                    local_changes += 1

        if not local_changes:
            return match.group(0)

        changed += local_changes
        return open_tag + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + close_tag

    return script_re.sub(clean_script, text), changed

def main():
    files = [p for p in Path(".").rglob("*.html") if should_scan(p)]

    changed_files = []
    total_changes = 0

    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        original = text

        text, c1 = clean_jsonld_faqs(text)
        text, c2 = clean_visible_faqs(text)

        count = c1 + c2

        if text != original:
            path.write_text(text, encoding="utf-8")
            changed_files.append((str(path), count))
            total_changes += count

    print("Files changed:", len(changed_files))
    print("FAQ answers changed:", total_changes)

    for path, count in changed_files[:100]:
        print(path, count)

if __name__ == "__main__":
    main()