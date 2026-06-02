from pathlib import Path
import re
import sys


def safe(text: str) -> str:
    return text.encode("ascii", "backslashreplace").decode("ascii")


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: find_module_by_keyword.py FILE KEYWORD")
    path = Path(".codex_remote") / sys.argv[1]
    keyword = sys.argv[2]
    text = path.read_text(encoding="utf-8", errors="ignore")
    for match in re.finditer(r'(?:(?P<quoted>"[^"]+")|(?P<bare>[A-Za-z0-9_$]+)):function\(', text):
        start = match.start()
        next_match = re.search(r',(?:"[^"]+"|[A-Za-z0-9_$]+):function\(', text[start + 1 :])
        end = start + 1 + next_match.start() if next_match else len(text)
        module = text[start:end]
        if keyword in module:
            key = match.group("quoted") or match.group("bare")
            print(safe(f"module={key} start={start} end={end} length={len(module)}"))
            index = module.find(keyword)
            left = max(0, index - 3000)
            right = min(len(module), index + 5000)
            print(safe(module[left:right]))


if __name__ == "__main__":
    main()
