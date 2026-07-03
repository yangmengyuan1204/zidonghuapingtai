"""探测 factoryEdit 接口，定位 500 错误根因"""
import requests, json

BASE = "https://oemapi.rakumart.cn"
ADMIN_USER = "Y001"
ADMIN_PASS = "raku@123456``"
ADMIN_CODE = "wnm666"

s = requests.Session()
s.trust_env = False  # 绕过系统代理

# 1. 登录
r = s.post(f"{BASE}/admin.login", data={
    "username": ADMIN_USER, "password": ADMIN_PASS, "system": "1",
    "compute_token": "", "code": ADMIN_CODE
})
r.raise_for_status()
try:
    data = r.json().get("data", {})
except:
    print(f"   r.status={r.status_code}, text={r.text[:500]}")
    data = {}
token = data.get("access_token", "") if isinstance(data, dict) else ""
print(f"1. admin_login: token={token[:20] if token else 'NONE'}...")

s.headers.update({
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://oemadmin.rakumart.cn",
    "Referer": "https://oemadmin.rakumart.cn/",
})

# 2. 创建询价单
body = {
    "factory_urls": [
        "https://sale.1688.com/factory/card.html?spm=a260k.22464671.llq7jdxw.26.7e847a6eplJjaR&memberId=b2b-2400464062&aHdkaW5n_isCentral=true&aHdkaW5n_isGrayed=false&topOfferIds=640852182287,656851528464,627202527081,684110329453&aHdkaW5n_isUseGray=true"
    ],
    "sku_content": "测试SKU内容",
}
r = s.post(f"{BASE}/api/newInquiry", json=body)
print(f"2. newInquiry: status={r.status_code}, text={r.text[:300]}")

# 等一会让后端处理
import time
time.sleep(2)

# 3. 查询订单详情
r = s.post(f"{BASE}/admin/inquiryList", json={"page": 1, "limit": 10, "order_sn": ""})
list_data = r.json()
print(f"3. inquiryList: status={r.status_code}, json={json.dumps(list_data, ensure_ascii=False)[:300]}")

# 4. 获取第一个订单的 detail
order_sn = None
detail_list = []
if isinstance(list_data, dict) and list_data.get("data"):
    data_block = list_data["data"]
    items = data_block.get("data") if isinstance(data_block, dict) else []
    if items:
        order_sn = items[0].get("order_sn")
        print(f"   order_sn={order_sn}")
        r = s.post(f"{BASE}/admin/inquiryDetail", json={"order_sn": order_sn})
        detail = r.json()
        print(f"   detail keys: {list(detail.keys()) if isinstance(detail, dict) else type(detail)}")
        detail_data = detail.get("data", {}) if isinstance(detail, dict) else {}
        detail_list = detail_data.get("detail_list") or []
        print(f"   detail_list count={len(detail_list)}")

if detail_list:
    d_item = detail_list[0]
    detail_id = d_item.get("id")
    factory_url = d_item.get("factory_url") or ""
    factory_iid = d_item.get("factory_iid") or ""
    factory_name = d_item.get("factory_name") or "测试工厂"
    factory_province = d_item.get("factory_province") or "浙江省"
    factory_city = d_item.get("factory_city") or "杭州市"
    factory_img = "https://rakumart-oem.oss-ap-northeast-1.aliyuncs.com/20260703092250121555.jpg"
    salesman = d_item.get("salesman") or "测试业务员"
    salesman_phone = d_item.get("salesman_phone") or "13800000000"
    goods_url = d_item.get("goods_url") or ""

    import re
    def extract_iid(url):
        if not url:
            return ""
        m = re.search(r'[?&]memberid=([^&#\s]+)', url, re.IGNORECASE)
        return m.group(1) if m else ""

    parsed_iid = extract_iid(factory_url)
    print(f"\n   factory_url: {factory_url[:120]}...")
    print(f"   d_item factory_iid: '{factory_iid}'")
    print(f"   parsed_iid: '{parsed_iid}'")
    final_iid = factory_iid or parsed_iid
    print(f"   final_iid: '{final_iid}'")

    # 测试1: 带 factory_img
    print("\n--- Test 1: 带 factory_img ---")
    body1 = {
        "detail_id": detail_id,
        "factory_iid": final_iid,
        "factory_name": factory_name,
        "factory_province": factory_province,
        "factory_city": factory_city,
        "factory_img": factory_img,
        "factory_url": factory_url,
        "salesman": salesman,
        "salesman_phone": salesman_phone,
        "goods_url": goods_url,
    }
    r1 = s.post(f"{BASE}/admin/factoryEdit", json=body1)
    print(f"   status={r1.status_code}, body={r1.text[:500]}")

    # 测试2: 不带 factory_img (空字符串)
    print("\n--- Test 2: 不带 factory_img (空) ---")
    body2 = dict(body1)
    body2["factory_img"] = ""
    r2 = s.post(f"{BASE}/admin/factoryEdit", json=body2)
    print(f"   status={r2.status_code}, body={r2.text[:500]}")

    # 测试3: 完全模仿用户 curl
    print("\n--- Test 3: 完全模仿用户 curl ---")
    body3 = {
        "detail_id": detail_id,
        "factory_iid": final_iid,
        "factory_name": "   ",
        "factory_province": "",
        "factory_city": "",
        "factory_img": factory_img,
        "factory_url": factory_url,
        "salesman": "   ",
        "salesman_phone": "16688812342",
        "goods_url": "",
    }
    r3 = s.post(f"{BASE}/admin/factoryEdit", json=body3)
    print(f"   status={r3.status_code}, body={r3.text[:500]}")
else:
    print("No detail_list found, can't test factoryEdit")