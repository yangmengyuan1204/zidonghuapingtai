"""抓取 OEM 询价单详情，查找"报价样品费退还"对应字段名"""
import requests, json

base_url = "https://oemapi.rakumart.cn"
s = requests.Session()
s.trust_env = False

r = s.post(f"{base_url}/admin/login", json={"username": "admin", "password": "123456"})
token = r.json().get("data", {}).get("access_token") or ""

headers = {
    "Authorization": f"Bearer {token}",
    "Origin": "https://oemadmin.rakumart.cn",
    "Referer": "https://oem.rakumart.cn/",
    "Content-Type": "application/json",
}

# 查询最近创建的询价单详情
r = s.post(f"{base_url}/admin/inquiryDetail", json={"order_sn": "X20260703133155-15-OEM"}, headers=headers, timeout=10)
detail = r.json().get("data", {})

# 找 detail_list 中工厂报价相关字段
detail_list = detail.get("detail_list") or []
if detail_list:
    item = detail_list[0]
    # 打印所有字段名和值
    print("=== detail_list[0] 所有字段 ===")
    for k, v in sorted(item.items()):
        vstr = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        print(f"  {k}: {vstr[:100]}")
    
    # 搜索包含 return/refund/退还 的字段
    print("\n=== 含 return/refund/退还 的字段 ===")
    for k, v in item.items():
        if any(kw in k.lower() for kw in ['return', 'refund', 'price_return']):
            print(f"  {k}: {v}")
        if isinstance(v, dict):
            for k2, v2 in v.items():
                if any(kw in k2.lower() for kw in ['return', 'refund', 'price_return']):
                    print(f"  {k}.{k2}: {v2}")

# 也看 sku_detail 中的字段
print("\n=== sku_detail 字段 ===")
sku_detail = item.get("sku_detail") or []
if sku_detail and isinstance(sku_detail, list):
    s0 = sku_detail[0]
    if isinstance(s0, dict):
        for k, v in sorted(s0.items()):
            vstr = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            print(f"  sku_detail[0].{k}: {vstr[:100]}")

# 打印 detail 顶层的工厂相关字段
print("\n=== detail 顶层工厂/报价字段 ===")
for k, v in sorted(detail.items()):
    if any(kw in k.lower() for kw in ['factory', 'sample', 'freight', 'delivery', 'other_fee', 'return', 'refund']):
        vstr = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        print(f"  {k}: {vstr[:150]}")
