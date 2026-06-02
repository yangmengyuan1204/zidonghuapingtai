import re
from pathlib import Path


BASE = Path(__file__).resolve().parent
FILES = ["orderList.js", "fundsManagement.js", "inspection.js", "warehouse.js"]
CALL_RE = re.compile(r"\$api\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\(")


def safe(text: str) -> str:
    return text.encode("ascii", "backslashreplace").decode("ascii")


def main() -> None:
    calls: dict[str, set[str]] = {}
    for name in FILES:
        text = (BASE / name).read_text(encoding="utf-8", errors="ignore")
        for group, method in CALL_RE.findall(text):
            calls.setdefault(group, set()).add(method)
    for group in sorted(calls):
        print(f"\n[{group}]")
        for method in sorted(calls[group]):
            print(method)

    app = (BASE / "app_remote.js").read_text(encoding="utf-8", errors="ignore")
    all_methods = sorted({method for methods in calls.values() for method in methods})
    print("\n[MAPPINGS]")
    for method in all_methods:
        idx = app.find(method + ":")
        if idx < 0:
            idx = app.find(method)
        if idx < 0:
            continue
        start = max(0, idx - 120)
        end = min(len(app), idx + 280)
        print(safe(f"\n==== {method} @ {idx} ====\n{app[start:end]}"))


if __name__ == "__main__":
    main()
