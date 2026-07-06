import sys
import json
import time
import requests
from urllib.parse import urljoin
sys.path.append('D:\\A_zidonghuapingtai')
from app.script_common import BaseScript, BusinessException
from app.data_scripts import (
    OEM_SAMPLE_FULL_FLOW_NAME, _oem_client_login, _oem_admin_login, _call_admin_api,
    _oem_build_sku_info_from_quote, _oem_post_json, _oem_generate_sample_order_sn,
    _translate_oem_msg, OEM_DEFAULT_FRONTEND_ORIGIN
)

class OemSampleFullFlowScript(BaseScript):
    """OEM样品单全流程脚本，功能完全兼容原有run_oem_sample_full_flow_script函数"""
    def run(self):
        """执行样品单全流程"""
        try:
            warehouse_city = int(self.variables.get("warehouse_city") or 2)
            inquiry_order_sn = str(self.variables.get("order_sn") or self.variables.get("inquiry_order_sn") or "").strip()
            sku_list_raw = self.variables.get("sku_list")
            sample_order_sn = str(self.variables.get("sample_order_sn") or "").strip()

            # 阶段1：提出样品单
            if not sample_order_sn and inquiry_order_sn:
                # 前台登录
                client_token, user_id = _oem_client_login(self.session, self.base_url, self.variables, self.default_timeout)
                # 解析SKU列表
                sku_list = sku_list_raw
                if isinstance(sku_list, str):
                    try:
                        sku_list = json.loads(sku_list) if sku_list.strip().startswith("[") else []
                    except (json.JSONDecodeError, TypeError):
                        sku_list = []
                if not isinstance(sku_list, list):
                    sku_list = []
                for item in sku_list:
                    if isinstance(item, dict) and "option" not in item:
                        item["option"] = []
                
                gen_sample_sn = _oem_generate_sample_order_sn(self.variables, user_id, 1)
                body = {
                    "order_sn": gen_sample_sn,
                    "inquiry_detail_id": self.variables.get("inquiry_detail_id") or "",
                    "type": 1,
                    "sku_list": sku_list if sku_list else [{"sku_id": 1993, "num": 1, "option": []}],
                    "remark": "",
                    "warehouse_city": warehouse_city,
                }
                headers = {
                    "Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
                    "Authorization": f"Bearer {client_token}",
                    "Origin": self.variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN),
                    "Referer": self.variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN).rstrip("/") + "/",
                }
                url = urljoin(self.base_url.rstrip("/") + "/", "/api/newOrder")
                payload = {}
                for attempt in range(3):
                    try:
                        resp = self.session.post(url, json=body, headers=headers, timeout=self.default_timeout)
                        payload = resp.json()
                        break
                    except (requests.ConnectionError, requests.Timeout, ValueError):
                        if attempt < 2:
                            time.sleep(0.8 * (attempt + 1))
                else:
                    raise BusinessException(3001, "创建样品单请求失败")
                
                if not payload.get("success") or payload.get("code") not in (0, "0", None):
                    raise BusinessException(2002, f"创建样品单失败: {_translate_oem_msg(payload.get('msg'))}", detail=payload)
                sample_order_sn = str(payload.get("data") or "")
                self.variables["sample_order_sn"] = sample_order_sn

            if not sample_order_sn:
                sample_order_sn = inquiry_order_sn
            self.variables["order_sn"] = sample_order_sn

            # 阶段2-5：后台管理流程
            admin_token = _oem_admin_login(self.session, self.base_url, self.variables, self.default_timeout)
            
            # 翻译提交
            _call_admin_api(
                self.session, self.base_url, "/admin/samplesSubmitPurchase",
                {"order_sn": sample_order_sn, "warehouse_city": warehouse_city},
                self.default_timeout, admin_token, self.variables, None, "samplesSubmitPurchase"
            )
            
            # 开始确认
            _call_admin_api(
                self.session, self.base_url, "/admin/samplesStartConfirm",
                {"order_sn": sample_order_sn},
                self.default_timeout, admin_token, self.variables, None, "samplesStartConfirm"
            )
            
            # 采购确认→业务
            sku_info = _oem_build_sku_info_from_quote(sample_order_sn, self.session, self.base_url, self.default_timeout, admin_token, self.variables)
            quote_info = {
                "inquiry_other_fee": str(self.variables.get("inquiry_other_fee", "0.00")),
                "inquiry_freight": str(self.variables.get("inquiry_freight", "0.00")),
                "inquiry_delivery_time": int(self.variables.get("inquiry_delivery_time", 0)),
                "quote_other_fee": str(self.variables.get("quote_other_fee", "7")),
                "quote_freight": str(self.variables.get("quote_freight", "8")),
                "quote_delivery_time": str(self.variables.get("quote_delivery_time", "9")),
                "real_other_fee": str(self.variables.get("real_other_fee", "7")),
                "real_freight": str(self.variables.get("real_freight", "8")),
                "sku_info": sku_info,
            }
            _call_admin_api(
                self.session, self.base_url, "/admin/samplesConfirmed",
                {
                    "order_sn": sample_order_sn, "warehouse_city": warehouse_city,
                    "is_special_quote": bool(self.variables.get("is_special_quote", True)),
                    "y_response": str(self.variables.get("y_response", "")),
                    "quote_info": quote_info,
                },
                self.default_timeout, admin_token, self.variables, None, "samplesConfirmed"
            )
            
            # 业务开始报价
            _call_admin_api(
                self.session, self.base_url, "/admin/samplesStartQuote",
                {"order_sn": sample_order_sn},
                self.default_timeout, admin_token, self.variables, None, "samplesStartQuote"
            )
            
            # 报价给客户
            _call_admin_api(
                self.session, self.base_url, "/admin/samplesQuoteToUser",
                {"order_sn": sample_order_sn, "warehouse_city": warehouse_city},
                self.default_timeout, admin_token, self.variables, None, "samplesQuoteToUser"
            )
            
            # 阶段6：客户余额支付
            client_token2, _ = _oem_client_login(self.session, self.base_url, self.variables, self.default_timeout)
            pay_payload = _oem_post_json(
                self.session, self.base_url, "/api/balancePayOrder",
                {"order_sn": sample_order_sn, "coupon_id": str(self.variables.get("coupon_id") or "")},
                self.default_timeout, token=client_token2, is_admin=False, variables=self.variables,
            )
            if not pay_payload.get("success") or pay_payload.get("code") not in (0, "0", None):
                raise BusinessException(2001, f"余额支付失败: {_translate_oem_msg(pay_payload.get('msg'))}", detail=pay_payload)
            serial_number = str((pay_payload.get("data") or {}).get("serial_number") or "")
            
            # 阶段7：后台开始采购
            _call_admin_api(
                self.session, self.base_url, "/admin/samplesStartPurchase",
                {"order_sn": sample_order_sn},
                self.default_timeout, admin_token, self.variables, None, "samplesStartPurchase"
            )
            
            summary = {
                "order_sn": sample_order_sn,
                "inquiry_order_sn": inquiry_order_sn,
                "serial_number": serial_number,
                "reason": "OEM样品单全流程执行成功",
                "script_name": OEM_SAMPLE_FULL_FLOW_NAME
            }
            return self.success(summary)
        except Exception as e:
            return self.fail(e)

# 保留原有函数入口，兼容所有调用方
def run_oem_sample_full_flow_script(env, variables=None):
    script = OemSampleFullFlowScript(env, variables)
    return script.run();
