import requests
import json

r = requests.post('http://127.0.0.1:8000/api/auth/login',
                  json={'username': 'admin', 'password': '123456'}, timeout=10)
token = r.json()['access_token']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# First, test if the HAR order_sn works at all
print("=== Testing D20260703175344-15-OEM ===")
rq = requests.get('http://127.0.0.1:8000/api/oem/inquiry-full?order_sn=D20260703175344-15-OEM',
                  headers=headers, timeout=30)
data = rq.json().get('data', {})
records = data.get('list', [])
print(f'Records count: {len(records)}')
if records:
    first = records[0]
    print(f"Detail ID: {first.get('id')}")
    qd = first.get('quote_detail', {})
    li = qd.get('large_info', {})
    print(f"Large info keys: {list(li.keys())[:10]}")

    # Try creating with D20260703175344-15-OEM
    payload = {
        'project_id': 4, 'env_id': 3,
        'variables': {
            'order_sn': 'D20260703175344-15-OEM',
            'account': '12345678990', 'password': '123456',
            'inquiry_detail_id': str(first.get('id', '')),
            'warehouse_city': 1,
            'remark': '测试',
            'sku_list': json.dumps([{
                'sku_id': 2166,
                'num': 1,
                'option': [],
                'warehouse': [{'warehouse_type': 1, 'FNSKU': '', 'ASIN': '', 'image': ''}]
            }])
        }
    }
    r2 = requests.post('http://127.0.0.1:8000/api/data-scripts/oem-bulk-order',
                       headers=headers, json=payload, timeout=120)
    result = r2.json()
    print(f"Result: {result.get('result')}")
    print(f"Reason: {result.get('summary', {}).get('reason')}")

    # Check if steps before create_bulk_order succeeded
    log = result.get('log', {})
    if log:
        steps = log.get('steps', [])
        for s in steps:
            print(f"  Step {s.get('name')}: {json.dumps(s.get('response', {}), ensure_ascii=False)[:200]}")
