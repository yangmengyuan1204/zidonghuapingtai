import requests, json
base = "https://oemapi.rakumart.cn"
s = requests.Session()
r = s.post(base + "/admin/login", json={"username":"admin","password":"123456"},
           headers={"Origin":"https://oemadmin.rakumart.cn","Referer":"https://oemadmin.rakumart.cn/"})
atok = r.json()["data"]["access_token"]
common = {"Content-Type":"application/json","Authorization":f"Bearer {atok}",
          "Origin":"https://oemadmin.rakumart.cn","Referer":"https://oemadmin.rakumart.cn/"}
# 对比新询价单和成功询价单的关键字段
for sn, label in [("X20260701154839-15-OEM","新询价单"), ("X20260701115233-15-OEM","成功询价单")]:
    r = s.post(base + "/admin/inquiryDetail", json={"order_sn":sn}, headers=common, timeout=15)
    d = r.json()["data"]
    print(f"\n=== {label} ({sn}) ===")
    for k in ["id","user_id","user_status","y_admin_status","g_admin_status","factory_type",
              "goods_id","goods_no","goods_type","num","goods_class","y_id","p_id","g_id","f_id",
              "translate_submit_at","translate_at","first_inquiry_at","first_quote_at","inquiry_at"]:
        print(f"  {k}: {d.get(k)}")
    dl = d.get("detail_list") or []
    if dl:
        print(f"  detail_list[0] status: {dl[0].get('status')}")
        print(f"  detail_list[0].factory_iid: {dl[0].get('factory_iid')}")
