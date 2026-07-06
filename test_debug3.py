import requests
import json

# Test through the backend with the updated code
r = requests.post('http://127.0.0.1:8000/api/auth/login',
                  json={'username': 'admin', 'password': '123456'}, timeout=10)
token = r.json()['access_token']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# Test with minimal body (single option, simple sku_list)
payload = {
    'project_id': 4,
    'env_id': 3,
    'variables': {
        'order_sn': 'X20260703134325-15-OEM',
        'account': '12345678990',
        'password': '123456',
        'inquiry_detail_id': '1002',
        'warehouse_city': 1,
        'remark': '测试',
        'sku_list': json.dumps([{
            'sku_id': 1490,
            'num': 1,
            'option': [],
            'warehouse': [{'warehouse_type': 1, 'FNSKU': '', 'ASIN': '', 'image': ''}]
        }])
    }
}

print('Sending minimal body (empty options)...')
r2 = requests.post('http://127.0.0.1:8000/api/data-scripts/oem-bulk-order',
                   headers=headers, json=payload, timeout=120)
result = r2.json()
print(f'Result: {result.get("result")}')
print(f'Summary reason: {result.get("summary", {}).get("reason")}')
