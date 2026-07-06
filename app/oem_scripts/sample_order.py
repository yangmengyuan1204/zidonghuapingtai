import sys
import json
import time
import requests
from urllib.parse import urljoin
sys.path.append('D:\\A_zidonghuapingtai')
from app.script_common import BaseScript, BusinessException
from app.data_scripts import (
    OEM_SAMPLE_ORDER_SCRIPT_NAME, _oem_client_login, _translate_oem_msg, 
    _oem_generate_sample_order_sn, OEM_DEFAULT_FRONTEND_ORIGIN
)

class OemSampleOrderScript(BaseScript):
    """OEM样品单创建脚本，功能完全兼容原有run_oem_sample_order_script函数"""
    def validate_params(self) -> None:
        """参数校验"""
        order_sn = str(self.variables.get("order_sn") or "").strip()
        if not order_sn:
            raise BusinessException(1001, "缺少必填参数：询价单号 order_sn 不能为空")
        self.variables["order_sn"] = order_sn

    def _parse_sku_list(self, sku_list):
        """解析SKU列表，兼容原有逻辑"""
        if isinstance(sku_list, list):
            for item in sku_list:
                if isinstance(item, dict) and "option" not in item:
                    item["option"] = []
            return sku_list
        if isinstance(sku_list, str) and sku_list.strip().startswith("["):
            try:
                sku_list = json.loads(sku_list)
                for item in sku_list:
                    if isinstance(item, dict) and "option" not in item:
                        item["option"] = []
                return sku_list
            except (json.JSONDecodeError, TypeError):
                return []
        if isinstance(sku_list, str) and sku_list.strip():
            result = []
            for line in sku_list.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                try:
                    sku_id = int(parts[0].strip())
                    num = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else 1
                    result.append({"sku_id": sku_id, "num": num, "option": []})
                except (ValueError, IndexError):
                    continue
            return result
        return []

    def run(self):
        """执行样品单创建流程"""
        try:
            self.validate_params()
            # 前台登录
            client_token, user_id = _oem_client_login(self.session, self.base_url, self.variables, self.default_timeout)
            # 解析SKU列表
            sku_list = self._parse_sku_list(self.variables.get("sku_list"))
            # 生成样品单号
            sample_order_sn = _oem_generate_sample_order_sn(self.variables, user_id, 1)
            # 构造请求体
            body = {
                "order_sn": sample_order_sn,
                "inquiry_detail_id": self.variables.get("inquiry_detail_id") or str(self.variables.get("id") or ""),
                "type": 1,
                "sku_list": sku_list if sku_list else [{"sku_id": 1993, "num": 1, "option": []}],
                "remark": "",
                "warehouse_city": 2,
            }
            # 构造请求头
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {client_token}",
                "Origin": self.variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN),
                "Referer": self.variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN).rstrip("/") + "/",
            }
            url = urljoin(self.base_url.rstrip("/") + "/", "/api/newOrder")
            # 重试3次
            last_error = None
            payload = {}
            for attempt in range(3):
                try:
                    response = self.session.post(url, json=body, headers=headers, timeout=self.default_timeout)
                    payload = response.json()
                    break
                except (requests.ConnectionError, requests.Timeout, ValueError) as exc:
                    last_error = exc
                    if attempt < 2:
                        time.sleep(0.8 * (attempt + 1))
            else:
                raise BusinessException(3001, f"创建样品单请求失败: {last_error}")
            
            if not payload.get("success") or payload.get("code") not in (0, "0", None):
                raw_msg = payload.get("msg")
                raw_data = payload.get("data")
                translated_msg = _translate_oem_msg(raw_msg)
                hint = ""
                if isinstance(raw_data, str) and "Line:" in raw_data:
                    hint = "（可能原因：该询价单已被转过样品单或状态已变更，请确认询价单可用性）"
                raise BusinessException(2002, f"创建样品单失败: {translated_msg}{hint}", detail=payload)
            
            order_sn_out = str(payload.get("data") or "")
            summary = {
                "order_sn": order_sn_out,
                "inquiry_order_sn": self.variables["order_sn"],
                "sample_order_sn": sample_order_sn,
                "reason": "创建样品单成功",
                "script_name": OEM_SAMPLE_ORDER_SCRIPT_NAME
            }
            return self.success(summary)
        except Exception as e:
            return self.fail(e)

# 保留原有函数入口，兼容所有调用方
def run_oem_sample_order_script(env, variables=None):
    script = OemSampleOrderScript(env, variables)
    return script.run()
