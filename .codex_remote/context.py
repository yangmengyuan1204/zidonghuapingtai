from pathlib import Path
import sys


BASE = Path(__file__).resolve().parent


def safe(text: str) -> str:
    return text.encode("ascii", "backslashreplace").decode("ascii")


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: context.py FILE KEYWORD [WINDOW]")
    file_name = sys.argv[1]
    keyword = sys.argv[2]
    window = int(sys.argv[3]) if len(sys.argv) > 3 else 2500
    text = (BASE / file_name).read_text(encoding="utf-8", errors="ignore")
    start_at = 0
    for occurrence in range(1, 10):
        index = text.find(keyword, start_at)
        if index < 0:
            break
        start = max(0, index - window)
        end = min(len(text), index + window)
        print(safe(f"\n==== {file_name} :: {keyword} occurrence {occurrence} @ {index} ====\n{text[start:end]}"))
        start_at = index + len(keyword)


if __name__ == "__main__":
    main()
