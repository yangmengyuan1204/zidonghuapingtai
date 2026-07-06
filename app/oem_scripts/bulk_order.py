import sys
import json
sys.path.append('D:\\A_zidonghuapingtai')
from app.script_common import BaseScript, BusinessException
from app.data_scripts import (
    OEM_BULK_ORDER_NAME, _oem_client_login, fetch_oem_full_quote, 
    _oem_query_option_list, _oem_order_preview, _oem_build_option_for_sku,
    _oem_build_warehouse_for_sku, _oem_edit_sku_image, _oem_create_new_order, _as_int
)

class OemBulkOrderScript(BaseScript):
    """OEM大货单创建脚本，功能完全兼容原有run_oem_bulk_order_script函数"""
    def validate_params(self) -> None:
        """参数校验"""
        order_sn = str(self.variables.get("order_sn") or "").strip()
        if not order_sn:
            raise BusinessException(1001, "缺少必填参数：询价单号 order_sn 不能为空")
        self.variables["order_sn"] = order_sn
        
        sku_list = self.variables.get("sku_list")
        if not sku_list:
            raise BusinessException(1002, "缺少必填参数：SKU列表 sku_list 不能为空")
        self.variables["sku_list"] = sku_list

    def run(self):
        """执行大货单创建流程"""
        try:
            self.validate_params()
            # 阶段1：前台登录
            client_token, user_id = _oem_client_login(self.session, self.base_url, self.variables, self.default_timeout)
            
            # 阶段2：查询报价详情
            quote_data = fetch_oem_full_quote(self.variables["order_sn"], self.variables)
            if not quote_data:
                raise BusinessException(2003, f"询价单 {self.variables['order_sn']} 无报价数据或接口返回异常")
            
            detail_id = str(quote_data.get("detail_id") or self.variables.get("inquiry_detail_id") or "").strip()
            if not detail_id:
                records = quote_data.get("list") or []
                if records and isinstance(records[0], dict):
                    detail_id = str(records[0].get("id") or "").strip()
            if not detail_id:
                raise BusinessException(2004, "未能从询价单解析出 detail_id")
            
            quote_detail = quote_data.get("quote_detail") or {}
            large_info = quote_detail.get("large_info") or {}
            detail_list = quote_data.get("list") or []
            goods_name = (detail_list[0] if detail_list and isinstance(detail_list[0], dict) else {}).get("goods_name") or ""
            
            # 阶段3：查询option列表
            option_list = _oem_query_option_list(self.session, self.base_url, client_token, self.default_timeout, self.variables)
            
            # 阶段4：订单预览（type=2大货单）
            preview_data = _oem_order_preview(self.session, self.base_url, client_token, detail_id, self.default_timeout, self.variables)
            if not preview_data:
                raise BusinessException(2005, f"询价单 {self.variables['order_sn']}（detail_id={detail_id}）无大货报价信息，可能尚未完成报价或报价已过期")
            
            # 阶段5：解析SKU列表+上传图片+editSkuImage
            sku_list_raw = self.variables["sku_list"]
            if isinstance(sku_list_raw, str) and sku_list_raw.strip().startswith("["):
                try:
                    sku_list_raw = json.loads(sku_list_raw)
                except (json.JSONDecodeError, TypeError):
                    sku_list_raw = []
            elif not isinstance(sku_list_raw, list):
                sku_list_raw = []
            
            bulk_images_raw = self.variables.get("bulk_images") or ""
            if isinstance(bulk_images_raw, list):
                bulk_images = [u for u in bulk_images_raw if u]
            else:
                bulk_images = [line.strip() for line in str(bulk_images_raw).splitlines() if line.strip()]
            
            sku_list_body = []
            for idx, item in enumerate(sku_list_raw):
                if not isinstance(item, dict):
                    continue
                sku_id = item.get("sku_id") or item.get("goods_sku_id") or item.get("id")
                if sku_id is None:
                    continue
                try:
                    sku_id_int = int(sku_id)
                except (TypeError, ValueError):
                    sku_id_int = sku_id
                num = _as_int(item.get("num"), 1)
                opt_input = item.get("option")
                if isinstance(opt_input, list) and opt_input:
                    options = opt_input
                else:
                    options = _oem_build_option_for_sku(option_list, num)
                warehouses = _oem_build_warehouse_for_sku(idx, self.variables, bulk_images)
                sku_image_url = warehouses[0].get("image") if warehouses else ""
                if sku_image_url and isinstance(sku_id_int, int):
                    _oem_edit_sku_image(self.session, self.base_url, client_token, sku_id_int, sku_image_url, self.default_timeout, self.variables)
                sku_list_body.append({
                    "sku_id": sku_id_int,
                    "num": num,
                    "option": options,
                    "warehouse": warehouses,
                })
            
            if not sku_list_body:
                raise BusinessException(2006, "构造SKU下单列表失败，sku_list_body为空")
            
            # 阶段6：创建大货单
            remark = str(self.variables.get("remark") or "").strip()
            warehouse_city = _as_int(self.variables.get("warehouse_city"), 1)
            new_order_body = {
                "order_sn": self.variables["order_sn"],
                "inquiry_detail_id": detail_id,
                "type": 2,
                "sku_list": sku_list_body,
                "remark": remark,
                "warehouse_city": warehouse_city,
            }
            order_result = _oem_create_new_order(self.session, self.base_url, client_token, new_order_body, self.default_timeout, self.variables)
            new_order_sn = ""
            if isinstance(order_result, dict):
                new_order_sn = str(order_result.get("order_sn") or order_result.get("large_order_sn") or order_result.get("sn") or "")
            
            summary = {
                "order_sn": self.variables["order_sn"],
                "new_order_sn": new_order_sn,
                "detail_id": detail_id,
                "goods_name": goods_name,
                "factory_count": len(detail_list),
                "sku_count": len(sku_list_body),
                "option_count": len(option_list),
                "has_large": bool(large_info),
                "bulk_images_count": len(bulk_images),
                "warehouse_city": warehouse_city,
                "remark": remark,
                "script_name": OEM_BULK_ORDER_NAME
            }
            return self.success(summary)
        except Exception as e:
            return self.fail(e)

# 保留原有函数入口，兼容所有调用方
def run_oem_bulk_order_script(env, variables=None):
    script = OemBulkOrderScript(env, variables)
    return script.run()
