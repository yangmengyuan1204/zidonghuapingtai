from pathlib import Path


BASE = Path(__file__).resolve().parent
FILES = ["orderList.js", "fundsManagement.js", "inspection.js", "warehouse.js", "app_remote.js"]
KEYWORDS = [
    "待拍下商品",
    "标记待改价",
    "待财务付款",
    "交易号付款",
    "开始核查",
    "上架入库",
    "本次到货数",
    "purchase_no",
    "waitPayment",
    "mark",
    "putStorage",
    "storage",
    "checkGoods",
    "inspection",
    "rack",
    "warehouse",
]


def main() -> None:
    printed = 0
    for name in FILES:
        text = (BASE / name).read_text(encoding="utf-8", errors="ignore")
        for keyword in KEYWORDS:
            start_at = 0
            count = 0
            while count < 3:
                index = text.find(keyword, start_at)
                if index < 0:
                    break
                start = max(0, index - 500)
                end = min(len(text), index + 700)
                snippet = text[start:end].replace("<", "[").replace(">", "]")
                text_out = f"\n==== {name} :: {keyword} @ {index} ====\n{snippet}"
                print(text_out.encode("ascii", "backslashreplace").decode("ascii"))
                printed += 1
                count += 1
                start_at = index + len(keyword)
                if printed >= 90:
                    return


if __name__ == "__main__":
    main()
