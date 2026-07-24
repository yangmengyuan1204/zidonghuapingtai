"""查数据库当前抓取用例总数和模块分布。临时脚本,用完即删。"""
from collections import Counter
from app.database import SessionLocal
from app.models import ApiCase

db = SessionLocal()
cases = db.query(ApiCase).filter(ApiCase.case_name.like("[抓取]%")).all()
print(f"数据库 [抓取] 用例总数: {len(cases)}")

# 按 path 前缀分组
import re
cnt = Counter()
for c in cases:
    m = re.search(r'/(?:api/)?([a-zA-Z_]+)', c.url)
    if m:
        cnt[m.group(1)] += 1

print("\n=== 模块分布 ===")
for p, c in cnt.most_common():
    print(f"  {p}: {c}")

# 看 id 范围(判断这次新增了多少)
if cases:
    ids = [c.id for c in cases]
    print(f"\nID 范围: {min(ids)} - {max(ids)}")

db.close()
