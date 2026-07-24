"""第三轮全量抓取:温和参数,覆盖更多菜单。临时脚本,用完即删。"""
import json
import time
import requests

BASE = "http://127.0.0.1:8000"

r = requests.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "123456"}, timeout=5)
print("login:", r.status_code)
token = r.json().get("access_token", "")
headers = {"Authorization": f"Bearer {token}"}

print("\n=== 触发第三轮全量抓取(200 页,菜单点击 20,页间隔 1s,菜单间隔 5s) ===")
r2 = requests.post(f"{BASE}/api/api-harvester/crawl", headers=headers, json={
    "front_url": "https://jpweb.rakumart.cn/",
    "front_account": "12345678990", "front_password": "123456",
    "back_url": "https://jpmanage.rakumart.cn",
    "back_account": "Y001", "back_password": "xiaolin666@@"
}, timeout=10)
print("crawl:", r2.status_code, r2.text[:200])
if r2.status_code != 200:
    raise SystemExit(1)
task_id = r2.json().get("task_id")
print("task_id:", task_id)

# 轮询 50 分钟
final = None
last_status = None
for i in range(100):
    time.sleep(30)
    try:
        r3 = requests.get(f"{BASE}/api/api-harvester/task/{task_id}", headers=headers, timeout=5)
        t = r3.json()
    except Exception as e:
        print(f"[{i*30}s] 轮询异常: {e}")
        continue
    elapsed = i * 30
    status = t.get("status", "unknown")
    if status != last_status or elapsed % 60 == 0:
        print(f"[{elapsed}s] status={status}")
        last_status = status
    if status != "running":
        final = t
        print(f"[{elapsed}s] status={status} error={t.get('error')}")
        break

if not final or final.get("status") != "done":
    print("抓取失败或超时,检查数据库已抓用例数")
    raise SystemExit(2)

print("\n=== 抓取结果 ===")
print("stats:", final["result"]["stats"])
eps = final["result"]["endpoints"]
back = [e for e in eps if e.get("source") == "back"]
print(f"接口: {len(eps)} (前台 {len(eps)-len(back)} + 后台 {len(back)})")

with open("crawl_round3.json", "w", encoding="utf-8") as f:
    json.dump({"crawl": final}, f, ensure_ascii=False, indent=2)
print("\n抓取结果已存 crawl_round3.json")

print("\n=== AI 分析 + 入库 ===")
r4 = requests.post(f"{BASE}/api/api-harvester/analyze", headers=headers, json={"task_id": task_id}, timeout=600)
print("analyze:", r4.status_code)
if r4.status_code == 200:
    result = r4.json()
    print("导入用例数:", result.get("imported_count"))
    analysis = result.get("analysis") or {}
    suggestions = analysis.get("script_suggestions") or []
    print(f"造数脚本建议: {len(suggestions)} 个")
    for i, s in enumerate(suggestions, 1):
        print(f"  {i}. {s.get('name','')} (步骤:{len(s.get('steps',[]))})")
    with open("analyze_round3.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("分析结果已存 analyze_round3.json")
