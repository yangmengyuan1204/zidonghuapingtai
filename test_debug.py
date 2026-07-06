import requests
import json

# Login
r = requests.post('http://127.0.0.1:8000/api/auth/login',
                  json={'username': 'admin', 'password': '123456'}, timeout=10)
token = r.json()['access_token']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# Get quote data with full details
rq = requests.get('http://127.0.0.1:8000/api/oem/inquiry-full?order_sn=X20260703134325-15-OEM',
                  headers=headers, timeout=30)
data = rq.json().get('data', {})
records = data.get('list', [])
first = records[0] if records else {}

# Check inquiry_detail_id
print(f"inquiry_detail_id: {first.get('id')}")

# Check large_info for this inquiry
qd = first.get('quote_detail', {})
li = qd.get('large_info', {})
bulk_skus = li.get('skus', [])
print(f"Bulk SKU count: {len(bulk_skus)}")
for s in bulk_skus:
    print(f"  SKU: {s.get('sku')}, min_qty: {s.get('large_min_quantity')}, price: {s.get('large_price')}")

# Check raw SKU list
raw_list = first.get('sku_detail', first.get('sku_list', []))
print(f"\nRaw SKU count: {len(raw_list)}")
for i, item in enumerate(raw_list):
    print(f"  [{i}] sku_id={item.get('goods_sku_id', item.get('sku_id'))}, sku={item.get('sku')}, moq={item.get('large_min_quantity', item.get('moq'))}")

# Get options
opt_resp = requests.get('http://127.0.0.1:8000/api/oem/option-list', headers=headers, timeout=30)
options = opt_resp.json().get('data', [])
print(f"\nOptions count: {len(options)}")

# Test 1: Try with num=1 and FNSKU='TEST-FNSKU-001' (matching record 602 that passed)
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

print("\n=== Test 1: num=1, all options, FNSKU='TEST-FNSKU-001' ===")
payload = {
    'project_id': 4, 'env_id': 3,
    'variables': {
        'order_sn': 'X20260703134325-15-OEM',
        'account': '12345678990', 'password': '123456',
        'inquiry_detail_id': str(first.get('id', '1002')),
        'warehouse_city': 1,
        'remark': '测试',
        'sku_list': json.dumps([{
            'sku_id': 1490,
            'num': 1,
            'option': build_opts(1),
            'warehouse': [{'warehouse_type': 1, 'FNSKU': 'TEST-FNSKU-001', 'ASIN': 'TEST-ASIN-001', 'image': ''}]
        }])
    }
}
r2 = requests.post('http://127.0.0.1:8000/api/data-scripts/oem-bulk-order',
                   headers=headers, json=payload, timeout=120)
result = r2.json()
print(f"Result: {result.get('result')}, new_order_sn: {result.get('summary', {}).get('new_order_sn')}")
if result.get('result') == 'failed':
    print(f"Error: {result.get('summary', {}).get('reason')}")

# Test 2: Try with just one option (like record 602)
print("\n=== Test 2: num=1, single option (id=10), FNSKU='TEST-FNSKU-001' ===")
payload['variables']['sku_list'] = json.dumps([{
    'sku_id': 1490,
    'num': 1,
    'option': [{'id': 10, 'name': '单面印刷', 'price': '1.00', 'price_type': 0, 'remark': '', 'unit': '元',
                'sort': 0, 'price_range': [], 'num': 1, 'checked': True, 'large_price': '2.00'}],
    'warehouse': [{'warehouse_type': 1, 'FNSKU': 'TEST-FNSKU-001', 'ASIN': 'TEST-ASIN-001', 'image': ''}]
}])
r3 = requests.post('http://127.0.0.1:8000/api/data-scripts/oem-bulk-order',
                   headers=headers, json=payload, timeout=120)
result3 = r3.json()
print(f"Result: {result3.get('result')}, new_order_sn: {result3.get('summary', {}).get('new_order_sn')}")
if result3.get('result') == 'failed':
    print(f"Error: {result3.get('summary', {}).get('reason')}")
