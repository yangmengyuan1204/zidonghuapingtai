from pathlib import Path
import sys


def safe(text: str) -> str:
    return text.encode("ascii", "backslashreplace").decode("ascii")


def find_module(text: str, key: str) -> str | None:
    patterns = [f'"{key}":function', f"{key}:function", f'"{key}":(function', f"{key}:(function"]
    for pattern in patterns:
        index = text.find(pattern)
        if index < 0:
            continue
        brace = text.find("{", index)
        if brace < 0:
            continue
        depth = 0
        in_string = ""
        escaped = False
        for pos in range(brace, len(text)):
            char = text[pos]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == in_string:
                    in_string = ""
                continue
            if char in ("'", '"', "`"):
                in_string = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[index : pos + 1]
    return None


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: extract_module.py FILE MODULE [KEYWORD]")
    path = Path(".codex_remote") / sys.argv[1]
    key = sys.argv[2]
    keyword = sys.argv[3] if len(sys.argv) > 3 else ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    module = find_module(text, key)
    if module is None:
        print(f"module {key!r} not found")
        return
    if keyword:
        start = 0
        found = False
        for occurrence in range(1, 20):
            index = module.find(keyword, start)
            if index < 0:
                break
            found = True
            left = max(0, index - 3000)
            right = min(len(module), index + 4500)
            print(safe(f"\n==== occurrence {occurrence} @ {index} ====\n{module[left:right]}"))
            start = index + len(keyword)
        if not found:
            print(f"keyword {keyword!r} not found in module {key!r}; module length={len(module)}")
        return
    print(safe(module[:30000]))
    if len(module) > 30000:
        print(safe(f"\n... truncated, module length={len(module)}"))


if __name__ == "__main__":
    main()
