"""重置 admin 密码为 admin123，然后调 API 走一遍 OEM 全流程"""
import sqlite3, json, requests
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 0. 保存旧密码
conn = sqlite3.connect("d:/A_zidonghuapingtai/auto_test_platform.db")
cur = conn.cursor()
cur.execute("SELECT password FROM user WHERE username = 'admin'")
old_hash = cur.fetchone()[0]
print(f"0. 旧密码已保存")

# 1. 重置密码
new_hash = pwd_context.hash("admin123")
cur.execute("UPDATE user SET password = ? WHERE username = 'admin'", (new_hash,))
conn.commit()
conn.close()
print(f"1. 密码已重置为 admin123")

# 2. 登录
s = requests.Session()
s.trust_env = False

r = s.post("http://127.0.0.1:8000/api/auth/login", json={"username": "admin", "password": "admin123"})
print(f"2. login: {r.status_code}")
data = r.json()
token = data.get("access_token") or data.get("token") or ""
print(f"   token: {token[:30]}...")
s.headers["Authorization"] = f"Bearer {token}"

# 3. 调 OEM 全流程
variables = {
    "factory_urls": "https://sale.1688.com/factory/card.html?spm=a260k.22464671.llq7jdxw.26.7e847a6eplJjaR&memberId=b2b-2400464062&aHdkaW5n_isCentral=true&aHdkaW5n_isGrayed=false&topOfferIds=640852182287,656851528464,627202527081,684110329453&aHdkaW5n_isUseGray=true",
    "factory_type": "3",
    "salesman_phone": "13800000000",
    "samples_price": "12.00",
    "large_price": "11.00",
    "large_other_fee": "12.00",
    "large_freight": "11.00",
    "large_delivery_time": 15,
    "large_deposit_rate": "100",
    "real_samples_price": "10.00",
    "real_large_price": "10.00",
}

r = s.post("http://127.0.0.1:8000/api/data-scripts/oem-full-inquiry-flow", json=variables)
print(f"3. run: {r.status_code}")
result = r.json()
print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])

# 4. 恢复密码
conn = sqlite3.connect("d:/A_zidonghuapingtai/auto_test_platform.db")
cur = conn.cursor()
cur.execute("UPDATE user SET password = ? WHERE username = 'admin'", (old_hash,))
conn.commit()
conn.close()
print(f"4. 密码已恢复")