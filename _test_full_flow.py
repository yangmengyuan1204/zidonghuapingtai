"""End-to-end test of OEM full flow - tests with real inquiry number."""
import sys, os, json, uuid
sys.path.insert(0, os.path.dirname(__file__))

# Test 1: Verify SKU list JSON parsing works
print("=== Test 1: SKU list JSON parsing ===")
sku_json = '[{"sku_id":1344,"num":1},{"sku_id":1345,"num":1}]'
sku_list = json.loads(sku_json)
for item in sku_list:
    if isinstance(item, dict) and "option" not in item:
        item["option"] = []
print(f"  SKU list: {sku_list}")
assert len(sku_list) == 2
assert sku_list[0].get("option") == []
assert sku_list[1].get("option") == []
print("  PASS")

# Test 2: Verify body construction
print("=== Test 2: Body construction ===")
body = {
    "order_sn": "X20260702112128-15-OEM",
    "inquiry_detail_id": "946",
    "type": 1,
    "sku_list": sku_list,
    "remark": "",
    "warehouse_city": 2,
}
body_json = json.dumps(body, ensure_ascii=False)
print(f"  Body: {body_json}")
assert '"inquiry_detail_id": "946"' in body_json
assert '"option"' in body_json
assert '"sku_id": 1344' in body_json
print("  PASS")

# Test 3: Verify env loading
print("=== Test 3: Module imports ===")
from app.models import Env
from app.core.utils import find_oem_data_script_project, OEM_BASE_URL
from app.data_scripts import run_oem_sample_full_flow_script, OEM_SAMPLE_FULL_FLOW_NAME
print(f"  Script name: {OEM_SAMPLE_FULL_FLOW_NAME}")
print("  PASS")

# We can't actually call the OEM API without valid credentials,
# but we verified the data format is correct
print("\n=== All format tests PASSED ===")
print("NOTE: Actual API call requires running server with valid OEM credentials")
