import sys
import time
import requests
from urllib.parse import urljoin
sys.path.append('D:\\A_zidonghuapingtai')
from app.script_common import BaseScript, BusinessException
from app.data_scripts import (
    OEM_SCRIPT_NAME, _oem_client_login, _oem_parse_factory_urls, 
    OEM_DEFAULT_FRONTEND_ORIGIN as OEM_DEFAULT_FRONTEND_ORIGIN
)

class OemNewInquiryScript(BaseScript):
    """OEM创建询价单脚本，功能完全兼容原有run_oem_new_inquiry_script函数"""
    def run(self):
        """执行询价单创建流程"""
        try:
            # 前台登录
            client_token, user_id = _oem_client_login(self.session, self.base_url, self.variables, self.default_timeout)
            
            # 构造SKU信息
            sku_info = self.variables.get("sku_info")
            if not isinstance(sku_info, list):
                sku_info = [
                    {"sku": self.variables.get("sku1") or "sku1", "num": self.variables.get("sku1_num") or "1"},
                    {"sku": self.variables.get("sku2") or "sku2", "num": self.variables.get("sku2_num") or "2"},
                    {"sku": self.variables.get("sku3") or "sku3", "num": self.variables.get("sku3_num") or "3"},
                ]
            
            # 构造请求体
            body = {
                "goods_name": self.variables.get("goods_name") or "测试商品",
                "hope_min_price": self.variables.get("hope_min_price") or "1",
                "hope_max_price": self.variables.get("hope_max_price") or "100",
                "hope_futures": self.variables.get("hope_futures") or "10",
                "material": self.variables.get("material") or "",
                "sku_info": sku_info,
                "is_temporarily": False,
                "goods_type": int(self.variables.get("goods_type") or 1),
                "goods_detail": self.variables.get("goods_detail") or "",
                "num": int(self.variables.get("num") or sum(int(s.get("num") or 0) for s in sku_info)),
                "customize_detail": self.variables.get("customize_detail") or "",
                "factory_urls": _oem_parse_factory_urls(self.variables),
                "factory_type": int(self.variables.get("factory_type") or 3),
                "goods_file": self.variables.get("goods_file") or [],
                "goods_img": self.variables.get("goods_img") or "",
                "goods_other_img": self.variables.get("goods_other_img") or [],
                "provide_prototype": False,
                "register_forward": self.variables.get("register_forward") or "",
                "forward_order": self.variables.get("forward_order") or {"forward_sn": "", "num": "", "goods_value": ""},
            }
            
            # 构造请求头
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {client_token}",
                "Origin": self.variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN),
                "Referer": self.variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN).rstrip("/") + "/",
            }
            url = urljoin(self.base_url.rstrip("/") + "/", "/api/newInquiry")
            
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
                raise BusinessException(3001, f"创建询价单请求失败: {last_error}")
            
            if not payload.get("success") or payload.get("code") not in (0, "0", None):
                raise BusinessException(2007, f"创建询价单失败: {payload.get('msg')}", detail=payload)
            
            inquiry_sn = str(payload.get("data") or "")
            summary = {"inquiry_sn": inquiry_sn, "reason": "创建询价单成功", "script_name": OEM_SCRIPT_NAME}
            return self.success(summary)
        except Exception as e:
            return self.fail(e)

# 保留原有函数入口，兼容所有调用方
def run_oem_new_inquiry_script(env, variables=None):
    script = OemNewInquiryScript(env, variables)
    return script.run()
