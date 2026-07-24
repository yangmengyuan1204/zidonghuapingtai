"""全量抓取+分析(第二轮,补抓漏的菜单)。临时脚本,用完即删。"""
import json
import time
import requests

BASE = "http://127.0.0.1:8000"

r = requests.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "123456"}, timeout=5)
print("login:", r.status_code)
token = r.json().get("access_token", "")
headers = {"Authorization": f"Bearer {token}"}

print("\n=== 触发全量抓取(200 页上限,菜单点击 20,预计 15-25 分钟) ===")
r2 = requests.post(f"{BASE}/api/api-harvester/crawl", headers=headers, json={
    "front_url": "https://jpweb.rakumart.cn/",
    "front_account": "12345678990", "front_password": "123456",
    "back_url": "https://jpmanage.rakumart.cn",
    "back_account": "Y001", "back_password": "xiaolin666@@"
}, timeout=10)
print("crawl:", r2.status_code)
task_id = r2.json().get("task_id")
print("task_id:", task_id)

# 轮询 50 分钟
final = None
for i in range(100):
    time.sleep(30)
    r3 = requests.get(f"{BASE}/api/api-harvester/task/{task_id}", headers=headers, timeout=5)
    t = r3.json()
    elapsed = i * 30
    if elapsed % 60 == 0:
        print(f"[{elapsed}s] status={t['status']}")
    if t["status"] != "running":
        final = t
        print(f"[{elapsed}s] status={t['status']}")
        break

if not final or final["status"] != "done":
    print("抓取失败或超时:", final.get("error") if final else "超时")
    raise SystemExit(1)

print("\n=== 抓取结果 ===")
print("stats:", final["result"]["stats"])
eps = final["result"]["endpoints"]
back = [e for e in eps if e.get("source") == "back"]
print(f"接口: {len(eps)} (前台 {len(eps)-len(back)} + 后台 {len(back)})")
print(f"页面: 前 {len(final['result']['front_pages'])} + 后 {len(final['result']['back_pages'])}")

print("\n=== AI 分析 + 入库 ===")
r4 = requests.post(f"{BASE}/api/api-harvester/analyze", headers=headers, json={"task_id": task_id}, timeout=300)
print("analyze:", r4.status_code)
result = r4.json()
print("导入用例数:", result.get("imported_count"))
analysis = result.get("analysis") or {}
suggestions = analysis.get("script_suggestions") or []
print(f"造数脚本建议: {len(suggestions)} 个")
for i, s in enumerate(suggestions, 1):
    print(f"  {i}. {s.get('name','')} (步骤:{len(s.get('steps',[]))})")

with open("crawl_round2.json", "w", encoding="utf-8") as f:
    json.dump({"crawl": final, "analyze": result}, f, ensure_ascii=False, indent=2)
print("\n结果已存 crawl_round2.json")
