import sys, os
sys.path.insert(0, os.getcwd())
# 触发 app.main 初始化（建库/入库 OEM 用例）
import app.main  # noqa
from app.data_scripts import run_oem_full_inquiry_flow_script
from app.models import Env
from app.database import SessionLocal

db = SessionLocal()
from app.models import Project
oem_proj = db.query(Project).filter(Project.name == "oem-测试").first()
env = db.query(Env).filter(Env.project_id == oem_proj.id).order_by(Env.id.asc()).first() if oem_proj else None
if not env:
    print("未找到 OEM 环境")
    sys.exit(1)
print(f"使用环境: env_id={env.id} base_url={env.base_url} timeout={env.timeout}")

variables = {
    "goods_name": "全流程测试商品",
    "hope_min_price": "1",
    "hope_max_price": "100",
    "hope_futures": "10",
    "goods_type": 1,
    "factory_type": 3,
    "factory_urls": "https://sale.1688.com/factory/card.html?memberId=b2b-221602338875777154",
    "goods_img": "",
    "sku1": "sku1", "sku1_num": 1,
    "sku2": "sku2", "sku2_num": 2,
    "sku3": "sku3", "sku3_num": 3,
    "factory_img": "",
    "salesman": "测试业务员",
    "salesman_phone": "13800000000",
    "samples_price": "12.00",
    "large_price": "11.00",
    "large_other_fee": "12.00",
    "large_freight": "11.00",
    "large_delivery_time": 15,
    "large_deposit_rate": "100",
    "real_samples_price": "10.00",
    "real_large_price": "10.00",
    "skip_translate": False,
    "skip_inquiry": False,
    "skip_quote": False,
}

passed, log_text, report_path, summary = run_oem_full_inquiry_flow_script(env, variables)
print("\n=== 结果 ===")
print("passed:", passed)
print("summary:", summary)
print("\n=== 日志末尾 ===")
print(log_text[-2500:] if len(log_text) > 2500 else log_text)
