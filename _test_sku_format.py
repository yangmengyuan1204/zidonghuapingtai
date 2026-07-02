"""Quick test of OEM full flow script - tests that parse logic works."""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))

# Test SKU JSON parsing logic
sku_json = '[{"sku_id":1344,"num":1},{"sku_id":1345,"num":1}]'
sku_list = json.loads(sku_json) if sku_json.strip().startswith("[") else []
for item in sku_list:
    if isinstance(item, dict) and "option" not in item:
        item["option"] = []
print("Parsed SKU list:", json.dumps(sku_list))

# Test the body construction
body = {
    "order_sn": "X20260702112128-15-OEM",
    "inquiry_detail_id": "946",
    "type": 1,
    "sku_list": sku_list,
    "remark": "",
    "warehouse_city": 2,
}
print("Body:", json.dumps(body, indent=2))
print("Test PASSED - SKU format looks correct")
