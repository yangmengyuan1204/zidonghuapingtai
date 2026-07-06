import pytest
from app.oem_scripts.sample_balance_pay import run_oem_sample_balance_pay_script, OemSampleBalancePayScript
from app.models import Env

def test_oem_balance_pay_missing_order_sn():
    """测试缺少必填参数order_sn的场景"""
    env = Env(base_url="https://oem-test.example.com", timeout=25)
    success, msg, trace_id, detail = run_oem_sample_balance_pay_script(env, variables={})
    assert success is False
    assert "order_sn必填" in msg
    assert isinstance(trace_id, str) and len(trace_id) > 0
    assert detail.get("error_type") == "business"
    assert detail.get("code") == 1001

def test_oem_balance_pay_class_init():
    """测试类初始化正常"""
    env = Env(base_url="https://oem-test.example.com", timeout=25)
    script = OemSampleBalancePayScript(env, variables={"order_sn": "PO20240601001"})
    assert script.trace_id is not None
    assert script.base_url == "https://oem-test.example.com"
    assert script.variables["order_sn"] == "PO20240601001"

def test_oem_base_script_success_fail():
    """测试公共基类返回格式正确"""
    from app.script_common import BaseScript, BusinessException, SystemException
    class TestScript(BaseScript):
        def run(self):
            return self.success({"test": "ok"})
    
    env = Env(base_url="https://test.com", timeout=10)
    success, msg, trace_id, detail = TestScript(env, variables={}).run()
    assert success is True
    assert msg == "执行成功"
    assert trace_id == detail.get("trace_id")
    assert detail.get("test") == "ok"

def test_oem_base_script_business_exception():
    """测试业务异常返回正确"""
    from app.script_common import BaseScript, BusinessException
    class TestScript(BaseScript):
        def run(self):
            raise BusinessException(1001, "参数错误", "详细错误信息")
    
    env = Env(base_url="https://test.com", timeout=10)
    success, msg, trace_id, detail = TestScript(env, variables={}).run()
    assert success is False
    assert msg == "参数错误"
    assert detail.get("code") == 1001
    assert detail.get("msg") == "详细错误信息"
    assert detail.get("error_type") == "business"

def test_oem_base_script_system_exception():
    """测试系统异常返回正确"""
    from app.script_common import BaseScript, SystemException
    class TestScript(BaseScript):
        def run(self):
            raise SystemException(3001, "网络超时", "超时堆栈")
    
    env = Env(base_url="https://test.com", timeout=10)
    success, msg, trace_id, detail = TestScript(env, variables={}).run()
    assert success is False
    assert msg == "网络超时"
    assert detail.get("code") == 3001
    assert detail.get("trace") == "超时堆栈"
    assert detail.get("error_type") == "system"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
