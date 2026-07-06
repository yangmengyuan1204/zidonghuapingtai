import sys
import json
import requests
from urllib.parse import urljoin
sys.path.append('D:\\A_zidonghuapingtai')
from app.script_common import BaseScript, BusinessException
from app.data_scripts import (
    OEM_FULL_INQUIRY_SCRIPT_NAME, _oem_client_login, _oem_parse_factory_urls,
    _oem_post_json, _oem_query_inquiry_detail, _oem_admin_login, _oem_build_quote_to_factory_body,
    _as_int, OEM_DEFAULT_FRONTEND_ORIGIN
)

class OemFullInquiryFlowScript(BaseScript):
    """OEM询价全流程脚本，功能完全兼容原有run_oem_full_inquiry_flow_script函数"""
    def run(self):
        """执行询价全流程"""
        try:
            order_sn = str(self.variables.get("order_sn") or "").strip()
            admin_token = ""
            client_token = ""

            # 阶段1：创建询价单
            if not self.variables.get("skip_create") and not order_sn:
                # 前置校验工厂链接
                factory_urls = _oem_parse_factory_urls(self.variables)
                if not factory_urls:
                    raise BusinessException(2008, "创建询价单失败: 缺少 factory_urls，请配置工厂链接")
                
                # 前台登录
                client_token, user_id, _ = _oem_client_login(self.session, self.base_url, self.variables, self.default_timeout)
                # 构造SKU信息
                sku_info = self.variables.get("sku_info")
                if not isinstance(sku_info, list):
                    sku_info = [
                        {"sku": self.variables.get("sku1") or "sku1", "num": int(self.variables.get("sku1_num") or 1)},
                        {"sku": self.variables.get("sku2") or "sku2", "num": int(self.variables.get("sku2_num") or 2)},
                        {"sku": self.variables.get("sku3") or "sku3", "num": int(self.variables.get("sku3_num") or 3)},
                    ]
                
                create_body = {
                    "goods_name": self.variables.get("goods_name") or "测试商品",
                    "hope_min_price": self.variables.get("hope_min_price") or "1",
                    "hope_max_price": self.variables.get("hope_max_price") or "100",
                    "hope_futures": self.variables.get("hope_futures") or "10",
                    "material": self.variables.get("material") or "",
                    "sku_info": sku_info,
                    "is_temporarily": False,
                    "goods_type": int(self.variables.get("goods_type") or 1),
                    "goods_class": int(self.variables.get("goods_class") or 110),
                    "goods_detail": self.variables.get("goods_detail") or "",
                    "num": int(self.variables.get("num") or sum(int(s.get("num") or 0) for s in sku_info)),
                    "customize_detail": self.variables.get("customize_detail") or "",
                    "factory_urls": factory_urls,
                    "factory_type": int(self.variables.get("factory_type") or 3),
                    "goods_file": self.variables.get("goods_file") or [],
                    "goods_img": self.variables.get("goods_img") or "",
                    "goods_other_img": self.variables.get("goods_other_img") or [],
                    "provide_prototype": False,
                    "register_forward": self.variables.get("register_forward") or "",
                    "forward_order": self.variables.get("forward_order") or {"forward_sn": "", "num": "", "goods_value": ""},
                }
                
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/plain, */*",
                    "Authorization": f"Bearer {client_token}",
                    "Origin": self.variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN),
                    "Referer": self.variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN).rstrip("/") + "/",
                }
                url = urljoin(self.base_url.rstrip("/") + "/", "/api/newInquiry")
                response = self.session.post(url, json=create_body, headers=headers, timeout=self.default_timeout)
                payload = response.json()
                
                if not payload.get("success") or payload.get("code") not in (0, "0", None):
                    raise BusinessException(2007, f"创建询价单失败: {payload.get('msg')}", detail=payload)
                order_sn = str(payload.get("data") or "")
                self.variables["order_sn"] = order_sn

            # 阶段2：后台翻译+确认询价单
            if not self.variables.get("skip_translate"):
                # 后台登录
                admin_token = _oem_admin_login(self.session, self.base_url, self.variables, self.default_timeout)
                # 调用翻译接口
                translate_payload = _oem_post_json(
                    self.session, self.base_url, "/admin/translateInquiry",
                    {"order_sn": order_sn}, self.default_timeout,
                    token=admin_token, is_admin=True, variables=self.variables
                )
                if not translate_payload.get("success") or translate_payload.get("code") not in (0, "0", None):
                    raise BusinessException(2009, f"询价单翻译失败: {translate_payload.get('msg')}")
                # 确认询价单
                confirm_payload = _oem_post_json(
                    self.session, self.base_url, "/admin/confirmInquiry",
                    {"order_sn": order_sn}, self.default_timeout,
                    token=admin_token, is_admin=True, variables=self.variables
                )
                if not confirm_payload.get("success") or confirm_payload.get("code") not in (0, "0", None):
                    raise BusinessException(2010, f"询价单确认失败: {confirm_payload.get('msg')}")

            # 阶段3：询价阶段
            if not self.variables.get("skip_inquiry"):
                # 查询询价单详情
                detail = _oem_query_inquiry_detail(self.session, self.base_url, admin_token, order_sn, self.default_timeout, self.variables)
                detail_list = detail.get("detail_list") or []
                if not detail_list:
                    raise BusinessException(2011, f"询价单{order_sn}没有可报价的detail项")
                
                # 逐个工厂报价
                for idx, d_item in enumerate(detail_list):
                    detail_id = d_item.get("id")
                    # 构造工厂报价请求体
                    quote_body = _oem_build_quote_to_factory_body(d_item, self.variables)
                    qp = _oem_post_json(
                        self.session, self.base_url, "/admin/factoryQuote", quote_body, self.default_timeout,
                        token=admin_token, is_admin=True, variables=self.variables
                    )
                    if not qp.get("success") and qp.get("code") not in (0, "0", None):
                        raise BusinessException(2012, f"工厂{idx+1}报价失败: {qp.get('msg')}", detail=qp)
                
                # 完成询价
                for d_item in detail_list:
                    d_item["status"] = 1
                detail["detail_list"] = detail_list
                detail["g_admin_status"] = 2
                cp = _oem_post_json(
                    self.session, self.base_url, "/admin/inquiryComplete", detail, self.default_timeout,
                    token=admin_token, is_admin=True, variables=self.variables
                )
                if not cp.get("success") and cp.get("code") not in (0, "0", None):
                    raise BusinessException(2013, f"询价完成失败: {cp.get('msg')}")

            # 阶段4：报价阶段
            if not self.variables.get("skip_quote"):
                detail = _oem_query_inquiry_detail(self.session, self.base_url, admin_token, order_sn, self.default_timeout, self.variables)
                detail_list = detail.get("detail_list") or []
                quote_admin = int(detail.get("g_id") or 19)
                factory_salesman_id = 236
                
                # 开始报价
                sq = _oem_post_json(
                    self.session, self.base_url, "/admin/inquiryStartQuote",
                    {"order_sn": order_sn}, self.default_timeout,
                    token=admin_token, is_admin=True, variables=self.variables
                )
                if not sq.get("success") and sq.get("code") not in (0, "0", None):
                    raise BusinessException(2014, f"开始报价失败: {sq.get('msg')}")
                
                # 逐个工厂报价给用户
                for idx, d_item in enumerate(detail_list):
                    detail_id = d_item.get("id")
                    quote_to_user_body = dict(d_item)
                    quote_to_user_body.update({
                        "status": 1, "is_read": 0,
                        "factory_salesman_id": factory_salesman_id,
                        "quote_admin": quote_admin,
                        "is_special_quote": False,
                        "is_temporarily": False,
                        "detail_id": detail_id,
                    })
                    qp2 = _oem_post_json(
                        self.session, self.base_url, "/admin/factoryQuoteToUser", quote_to_user_body, self.default_timeout,
                        token=admin_token, is_admin=True, variables=self.variables
                    )
                    if not qp2.get("success") and qp2.get("code") not in (0, "0", None):
                        raise BusinessException(2015, f"工厂{idx+1}报价给用户失败: {qp2.get('msg')}", detail=qp2)
                
                # 完成报价
                qc = _oem_post_json(
                    self.session, self.base_url, "/admin/inquiryQuoteComplate",
                    {"order_sn": order_sn}, self.default_timeout,
                    token=admin_token, is_admin=True, variables=self.variables
                )
                if not qc.get("success") and qc.get("code") not in (0, "0", None):
                    raise BusinessException(2016, f"报价完成失败: {qc.get('msg')}")

            summary = {
                "order_sn": order_sn,
                "reason": "OEM询价全流程执行成功",
                "script_name": OEM_FULL_INQUIRY_SCRIPT_NAME,
                "completed_phases": [
                    "create" if not self.variables.get("skip_create") else None,
                    "translate" if not self.variables.get("skip_translate") else None,
                    "inquiry" if not self.variables.get("skip_inquiry") else None,
                    "quote" if not self.variables.get("skip_quote") else None
                ]
            }
            return self.success(summary)
        except Exception as e:
            return self.fail(e)

# 保留原有函数入口，兼容所有调用方
def run_oem_full_inquiry_flow_script(env, variables=None):
    script = OemFullInquiryFlowScript(env, variables)
    return script.run();
