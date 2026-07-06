import requests
import json

# Direct OEM API call using session (like the actual code)
BASE = 'https://oemapi.rakumart.cn'
s = requests.Session()

headers_base = {'Content-Type': 'application/json',
                'Origin': 'https://oem.rakumart.cn',
                'Referer': 'https://oem.rakumart.cn/'}

# 1. Login
r = s.post(f'{BASE}/api/login', json={'account': '12345678990', 'password': '123456'},
           headers=headers_base, timeout=30)
print(f'Login status: {r.status_code}')
login_data = r.json()
print(f'Login response: {json.dumps(login_data, ensure_ascii=False, indent=2)[:500]}')
client_token = login_data.get('data', {}).get('access_token', '')
print(f'Token: {client_token[:40]}...')

auth_headers = {**headers_base, 'Authorization': f'Bearer {client_token}'}

# 2. Get option list
r3 = s.post(f'{BASE}/common/common/optionList', json={}, headers=auth_headers, timeout=30)
print(f'\nOptionList status: {r3.status_code}')
opts = r3.json()
print(f'OptionList response: {json.dumps(opts, ensure_ascii=False, indent=2)[:500]}')

# 3. Build and send newOrder with full option details
if opts.get('data'):
    options = opts['data']
    def build_opts(num):
        result = []
        for opt in options:
            item = dict(opt)
            is_photo = (item.get('id') == 9 or '拍照' in str(item.get('name', '')))
            item['num'] = 1 if is_photo else num
            item['checked'] = True
            if 'large_price' not in item:
                item['large_price'] = item.get('price', '0.00')
            if 'price_range' not in item:
                item['price_range'] = []
            result.append(item)
        return result

    order_body = {
        'order_sn': 'X20260703134325-15-OEM',
        'inquiry_detail_id': '1002',
        'type': 2,
        'sku_list': [{
            'sku_id': 1490,
            'num': 10,
            'option': build_opts(10),
            'warehouse': [{'warehouse_type': 1, 'FNSKU': '1', 'ASIN': '2', 'image': ''}]
        }],
        'remark': '测试',
        'warehouse_city': 1,
    }
    print(f'\n=== Sending newOrder ===')
    r4 = s.post(f'{BASE}/api/newOrder', json=order_body, headers=auth_headers, timeout=60)
    print(f'newOrder status: {r4.status_code}')
    resp = r4.json()
    print(f'newOrder response: {json.dumps(resp, ensure_ascii=False, indent=2)[:2000]}')
    print(f'\nFull response keys: {list(resp.keys()) if isinstance(resp, dict) else "N/A"}')
    if isinstance(resp, dict) and resp.get('data'):
        print(f'Response data: {json.dumps(resp.get("data"), ensure_ascii=False, indent=2)[:1000]}')
