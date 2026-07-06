import requests
import json
import time

# Login
r = requests.post('http://127.0.0.1:8000/api/auth/login',
                  json={'username': 'admin', 'password': '123456'}, timeout=10)
token = r.json()['access_token']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
print('Token obtained')

# Exactly replicate the HAR body (using same SKU IDs as in the inquiry)
# But we need to map the HAR structure to our inquiry (X20260703134325-15-OEM, detail_id=1002, SKU 1490/1491)
# First, let's get the option list to map option IDs
opt_resp = requests.get('http://127.0.0.1:8000/api/oem/option-list', headers=headers, timeout=30)
options = opt_resp.json().get('data', [])
print(f'Options: {len(options)}')
print(f'Option IDs: {[o.get("id") for o in options[:5]]}...')

# Build body matching HAR structure exactly
def build_full_option(opt_template, num):
    """Build option list matching HAR structure: all options, checked=true"""
    result = []
    for opt in opt_template:
        item = dict(opt)
        opt_id = item.get('id')
        opt_name = str(item.get('name', ''))
        # 拍照 id=9 or name contains 拍照 -> num=1
        is_photo = (opt_id == 9 or '拍照' in opt_name)
        item['num'] = 1 if is_photo else num
        item['checked'] = True
        # Ensure large_price exists
        if 'large_price' not in item:
            item['large_price'] = item.get('price', '0.00')
        # Ensure price_range exists
        if 'price_range' not in item:
            item['price_range'] = []
        result.append(item)
    return result

# Build SKU list matching HAR style (full option list for each SKU)
sku_list_body = [
    {
        'sku_id': 1490,
        'num': 10,
        'option': build_full_option(options, 10),
        'warehouse': [{'warehouse_type': 1, 'FNSKU': '1', 'ASIN': '2', 'image': ''}]
    }
]

payload = {
    'project_id': 4,
    'env_id': 3,
    'variables': {
        'order_sn': 'X20260703134325-15-OEM',
        'account': '12345678990',
        'password': '123456',
        'inquiry_detail_id': '1002',
        'warehouse_city': 1,
        'remark': '这是备注',
        'sku_list': json.dumps(sku_list_body),
    }
}

print(f'\nSending with SKU 1490, num=10, all {len(options)} options checked')
r2 = requests.post('http://127.0.0.1:8000/api/data-scripts/oem-bulk-order',
                   headers=headers, json=payload, timeout=120)
result = r2.json()
print(f'Result: {result.get("result")}')
if result.get('summary'):
    print(f'Summary: {json.dumps(result.get("summary", {}), ensure_ascii=False, indent=2)}')
