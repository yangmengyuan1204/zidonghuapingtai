import sys
sys.path.append('D:\\A_zidonghuapingtai')
from app.script_common import BaseScript, BusinessException
from app.data_scripts import (
    OEM_SAMPLE_ADMIN_SCRIPT_NAME, _oem_admin_login, _call_admin_api, _oem_build_sku_info_from_quote
)

class OemSampleAdminFlowScript(BaseScript):
    """OEM样品单后台审核流程脚本，功能完全兼容原有run_oem_sample_admin_flow_script函数"""
    def validate_params(self) -> None:
        """参数校验"""
        order_sn = str(self.variables.get("order_sn") or "").strip()
        if not order_sn:
            raise BusinessException(1001, "缺少必填参数：order_sn")
        self.variables["order_sn"] = order_sn

    def run(self):
        """执行后台审核流程"""
        try:
            self.validate_params()
            # 后台登录
            admin_token = _oem_admin_login(self.session, self.base_url, self.variables, self.default_timeout)
            
            # 1. 样品单翻译提交
            _call_admin_api(
                self.session, self.base_url, "/admin/samplesSubmitPurchase",
                {"order_sn": self.variables["order_sn"], "warehouse_city": int(self.variables.get("warehouse_city") or 2)},
                self.default_timeout, admin_token, self.variables, None, "samplesSubmitPurchase"
            )
            
            # 2. 样品单开始确认
            _call_admin_api(
                self.session, self.base_url, "/admin/samplesStartConfirm",
                {"order_sn": self.variables["order_sn"]},
                self.default_timeout, admin_token, self.variables, None, "samplesStartConfirm"
            )
            
            # 3. 采购确认→业务
            sku_info = _oem_build_sku_info_from_quote(self.variables["order_sn"], self.session, self.base_url, self.default_timeout, admin_token, self.variables)
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
                    "order_sn": self.variables["order_sn"],
                    "warehouse_city": int(self.variables.get("warehouse_city") or 2),
                    "is_special_quote": bool(self.variables.get("is_special_quote", True)),
                    "y_response": str(self.variables.get("y_response", "")),
                    "quote_info": quote_info,
                },
                self.default_timeout, admin_token, self.variables, None, "samplesConfirmed"
            )
            
            # 4. 业务开始报价
            _call_admin_api(
                self.session, self.base_url, "/admin/samplesStartQuote",
                {"order_sn": self.variables["order_sn"]},
                self.default_timeout, admin_token, self.variables, None, "samplesStartQuote"
            )
            
            # 5. 报价给客户
            _call_admin_api(
                self.session, self.base_url, "/admin/samplesQuoteToUser",
                {"order_sn": self.variables["order_sn"], "warehouse_city": int(self.variables.get("warehouse_city") or 2)},
                self.default_timeout, admin_token, self.variables, None, "samplesQuoteToUser"
            )
            
            summary = {
                "order_sn": self.variables["order_sn"],
                "reason": "样品单后台流程执行成功",
                "script_name": OEM_SAMPLE_ADMIN_SCRIPT_NAME
            }
            return self.success(summary)
        except Exception as e:
            return self.fail(e)

# 保留原有函数入口，兼容所有调用方
def run_oem_sample_admin_flow_script(env, variables=None):
    script = OemSampleAdminFlowScript(env, variables)
    return script.run();
