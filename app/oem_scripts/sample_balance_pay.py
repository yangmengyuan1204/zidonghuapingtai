import sys
sys.path.append('D:\\A_zidonghuapingtai')
from app.script_common import BaseScript, BusinessException
from app.data_scripts import OEM_BALANCE_PAY_NAME

class OemSampleBalancePayScript(BaseScript):
    """OEM样品单余额支付脚本，功能完全兼容原有run_oem_sample_balance_pay_script函数"""
    def validate_params(self) -> None:
        """参数校验"""
        order_sn = str(self.variables.get("order_sn") or "").strip()
        if not order_sn:
            raise BusinessException(1001, "缺少必填参数：order_sn")
        self.variables["order_sn"] = order_sn

    def run(self):
        """执行支付流程"""
        try:
            # 参数校验
            self.validate_params()
            # 前台登录
            from app.data_scripts import _oem_client_login, _oem_post_json, _translate_oem_msg, _step
            client_token, _, _ = _oem_client_login(self.session, self.base_url, self.variables, self.default_timeout)
            # 调用支付接口
            payload = _oem_post_json(
                self.session, self.base_url, "/api/balancePayOrder",
                {"order_sn": self.variables["order_sn"], "coupon_id": str(self.variables.get("coupon_id") or "")},
                self.default_timeout, token=client_token, is_admin=False, variables=self.variables
            )
            if not payload.get("success") or payload.get("code") not in (0, "0", None):
                raise BusinessException(2001, f"余额支付失败: {_translate_oem_msg(payload.get('msg'))}", detail=payload.get("msg"))
            
            data = payload.get("data") or {}
            serial_number = str(data.get("serial_number") or "")
            summary = {"order_sn": self.variables["order_sn"], "serial_number": serial_number, "reason": "余额支付成功", "script_name": OEM_BALANCE_PAY_NAME}
            return self.success(summary)
        except Exception as e:
            return self.fail(e)


# 保留原有函数入口，兼容所有调用方，底层自动调用新的类，不需要修改任何调用代码
def run_oem_sample_balance_pay_script(env, variables=None):
    script = OemSampleBalancePayScript(env, variables)
    return script.run()
