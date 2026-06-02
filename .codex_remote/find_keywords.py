from pathlib import Path
import sys


def main() -> None:
    keywords = sys.argv[1:] or ["d1bd"]
    for path in sorted(Path(".codex_remote").glob("*.js")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        hits = {keyword: text.find(keyword) for keyword in keywords if keyword in text}
        if hits:
            print(path.name, hits)


if __name__ == "__main__":
    main()
