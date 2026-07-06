import traceback


class BusinessException(Exception):
    """业务异常：可预期的业务错误，如参数校验失败、接口返回业务错误等"""
    def __init__(self, code: int, msg: str, detail: str = None):
        self.code = code
        self.msg = msg
        self.detail = detail or msg
        self.trace = None
        super().__init__(self.msg)


class SystemException(Exception):
    """系统异常：非预期的系统错误，如网络超时、服务不可用等"""
    def __init__(self, code: int, msg: str, trace: str = None):
        self.code = code
        self.msg = msg
        self.trace = trace or traceback.format_exc()
        super().__init__(self.msg)
