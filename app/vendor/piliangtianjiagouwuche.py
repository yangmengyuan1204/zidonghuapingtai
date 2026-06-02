#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量搜索衣服商品，并按"100 个店铺，每店铺 3 个不同商品/规格"的规则加入购物车。

默认是预演模式，不会真的添加购物车；确认预览无误后，加 --execute 才会真实执行。

运行示例：
  python rakumart_add_cart_bulk.py --account 1234567890 --password 123456 --keyword 衣服
  python rakumart_add_cart_bulk.py --account 1234567890 --password 123456 --keyword 衣服 --execute

依赖：
  pip install requests
"""

# 从 __future__ 导入 print_function，确保 Python 2/3 兼容性
from __future__ import print_function

# 导入必要的标准库模块
import argparse      # 用于解析命令行参数
import json          # 用于处理 JSON 数据
import os            # 用于操作系统相关功能，如文件路径
import subprocess    # 用于调用外部命令（如 curl）
import sys           # 用于系统相关功能，如标准输入输出
import threading     # 用于多线程
import time          # 用于时间相关功能，如睡眠
from collections import OrderedDict  # 导入有序字典，保持插入顺序

# 导入 unicode 类型（Python 2/3 兼容性处理）
from cffi.backend_ctypes import unicode

# 尝试导入 ThreadPool，如果失败则设为 None
# ThreadPool 用于并行处理商品详情请求
try:
    from multiprocessing.pool import ThreadPool
except Exception:
    ThreadPool = None

# 尝试导入 requests 库，如果失败则设为 None
# requests 是 Python 流行的 HTTP 请求库
try:
    import requests
except ImportError:
    requests = None


# 定义 Rakumart API 的基础 URL
BASE_URL = "https://jpapi.rakumart.cn"

# 定义 text_type 为 unicode 或 str（Python 2/3 兼容性）
try:
    text_type = unicode
except NameError:
    text_type = str


def pick(data, *keys):
    """
    从字典中按优先级获取第一个非空值。
    
    参数:
        data: 要查找的字典
        *keys: 按优先级排列的键名列表
        最后一个参数可以是 {"default": 默认值} 形式的字典
    
    返回:
        找到的第一个非空值，如果没有则返回默认值
    """
    default = ""  # 默认返回值
    # 检查最后一个参数是否是包含 default 的字典
    if keys and isinstance(keys[-1], dict) and "default" in keys[-1]:
        default = keys[-1]["default"]  # 提取默认值
        keys = keys[:-1]  # 从键列表中移除默认值参数
    # 遍历所有键，返回第一个存在的非空值
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default  # 如果没有找到，返回默认值


def to_text(value):
    """
    将任意值转换为文本字符串。
    
    参数:
        value: 任意类型的值
    
    返回:
        字符串形式的值
    """
    if value is None:
        return ""  # None 转为空字符串
    if isinstance(value, text_type):
        return value  # 如果已经是文本类型，直接返回
    return str(value)  # 其他类型转为字符串


def to_unicode_text(value):
    """
    将任意值转换为 Unicode 文本字符串（处理编码问题）。
    
    参数:
        value: 任意类型的值
    
    返回:
        Unicode 字符串
    """
    if value is None:
        return u""  # None 转为空 Unicode 字符串
    if isinstance(value, text_type):
        return value  # 如果已经是文本类型，直接返回
    if isinstance(value, str):
        # 尝试多种编码解码
        for encoding in ("utf-8", sys.getfilesystemencoding() or "", "mbcs"):
            if not encoding:
                continue
            try:
                return value.decode(encoding)  # 解码为 Unicode
            except Exception:
                pass  # 解码失败，尝试下一个编码
    return text_type(value)  # 最后尝试直接转换


def json_ready(value):
    """
    递归将数据转换为 JSON 安全的格式（确保所有字符串都是 Unicode）。
    
    参数:
        value: 任意类型的数据
    
    返回:
        JSON 安全的数据
    """
    if isinstance(value, dict):
        # 递归处理字典的键和值
        return dict((to_unicode_text(k), json_ready(v)) for k, v in value.items())
    if isinstance(value, list):
        # 递归处理列表的每个元素
        return [json_ready(x) for x in value]
    if isinstance(value, tuple):
        # 递归处理元组的每个元素
        return [json_ready(x) for x in value]
    if isinstance(value, str) and not isinstance(value, text_type):
        # 将非 Unicode 字符串转为 Unicode
        return to_unicode_text(value)
    return value  # 其他类型直接返回


def to_http_bytes(value):
    """
    将值转换为 HTTP 请求可用的字节串。
    
    参数:
        value: 任意类型的值
    
    返回:
        字节串
    """
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return to_text(value).encode("utf-8")


def curl_escape(value):
    """
    对值进行转义，以便在 curl 命令中安全使用。
    
    参数:
        value: 要转义的值
    
    返回:
        转义后的字符串
    """
    if isinstance(value, bytes):
        raw = value.decode("utf-8", errors="replace")
    else:
        raw = to_text(value)
    raw = raw.replace("\\", "\\\\").replace('"', '\\"')
    return raw.replace("\r", "\\r").replace("\n", "\\n")


def json_text(value):
    """
    将值转换为 JSON 文本字符串。
    
    参数:
        value: 要转换的值
    
    返回:
        JSON 字符串
    """
    if isinstance(value, text_type):
        return value  # 如果已经是文本类型，直接返回
    # 否则转为 JSON 字符串，不转义非 ASCII 字符
    return json.dumps(json_ready(value), ensure_ascii=False, separators=(",", ":"))


def as_list(value):
    """
    将值转换为列表。
    
    参数:
        value: 任意类型的值
    
    返回:
        列表形式的值
    """
    if value is None:
        return []  # None 转为空列表
    if isinstance(value, list):
        return value  # 如果已经是列表，直接返回
    if isinstance(value, dict):
        return list(value.values())  # 字典转为值列表
    return [value]  # 其他类型包装为单元素列表


def log(message, error=False):
    """
    打印日志消息到标准输出或标准错误。
    
    参数:
        message: 要打印的消息
        error: 是否为错误消息（True 则输出到 stderr）
    """
    stream = sys.stderr if error else sys.stdout  # 选择输出流
    print(message, file=stream)  # 打印消息
    try:
        stream.flush()  # 刷新缓冲区，确保立即输出
    except Exception:
        pass  # 刷新失败则忽略


def parse_int(value, default=0):
    """
    将值解析为整数。
    
    参数:
        value: 要解析的值
        default: 解析失败时的默认值
    
    返回:
        整数形式的值，或默认值
    """
    try:
        return int(float(value))  # 先转浮点数再转整数
    except Exception:
        return default  # 解析失败返回默认值


class CartItem(object):
    """
    购物车商品项类。
    
    封装了添加到购物车所需的商品信息。
    """
    def __init__(
        self,
        goods_id,        # 商品ID
        goods_title,     # 商品标题
        price,           # 商品价格
        num,             # 购买数量
        pic,             # 商品图片URL
        detail,          # 商品规格详情（JSON字符串）
        sku_id,          # SKU ID
        spec_id,         # 规格ID
        shop_id,         # 店铺ID
        shop_name,       # 店铺名称
        from_platform,   # 来源平台（如1688）
        price_ranges,    # 价格区间（JSON字符串）
        trace,           # 追踪标识
    ):
        # 初始化所有属性
        self.goods_id = goods_id
        self.goods_title = goods_title
        self.price = price
        self.num = num
        self.pic = pic
        self.detail = detail
        self.sku_id = sku_id
        self.spec_id = spec_id
        self.shop_id = shop_id
        self.shop_name = shop_name
        self.from_platform = from_platform
        self.price_ranges = price_ranges
        self.trace = trace

    def to_dict(self):
        """
        将购物车项转换为字典格式。
        
        返回:
            包含所有属性的字典
        """
        return {
            "goods_id": self.goods_id,
            "goods_title": self.goods_title,
            "price": self.price,
            "num": self.num,
            "pic": self.pic,
            "detail": self.detail,
            "sku_id": self.sku_id,
            "spec_id": self.spec_id,
            "shop_id": self.shop_id,
            "shop_name": self.shop_name,
            "from_platform": self.from_platform,
            "price_ranges": self.price_ranges,
            "trace": self.trace,
        }


class RakumartClient(object):
    """
    Rakumart API 客户端类。
    
    封装了与 Rakumart 平台 API 交互的所有方法。
    """
    def __init__(self, base_url, timeout):
        """
        初始化客户端。
        
        参数:
            base_url: API 基础 URL
            timeout: 请求超时时间（秒）
        """
        # 检查 requests 库是否已安装
        if requests is None:
            raise RuntimeError("Missing dependency: requests. Install it with: pip install requests")
        self.base_url = base_url.rstrip("/")  # 去除末尾斜杠
        self.timeout = timeout  # 设置超时时间
        self.use_curl = False  # 是否使用 curl 作为备用方案
        self.session = requests.Session()  # 创建 HTTP 会话
        # 设置默认请求头
        self.session.headers.update(
            {
                "User-Agent": "RakumartBulkCart/1.0",  # 用户代理标识
                "Accept": "application/json, text/plain, */*",  # 接受的响应类型
            }
        )
        # 禁用SSL验证和系统代理（解决代理和证书问题）
        self.session.verify = False  # 不验证 SSL 证书
        self.session.trust_env = False  # 不使用系统代理设置
        from urllib3.exceptions import InsecureRequestWarning
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)  # 禁用 SSL 警告

    def post_form(self, path, fields):
        """
        发送 POST 表单请求。
        
        参数:
            path: API 路径
            fields: 表单字段字典
        
        返回:
            API 响应的 JSON 数据
        """
        # 构建完整 URL
        url = path if path.startswith("http") else self.base_url + path

        # 如果设置了使用 curl 或 requests 不可用，则使用 curl
        if self.use_curl or requests is None:
            return self.post_form_with_curl(url, fields)

        # API 文档要求使用 form-data 格式
        # (None, value) 会让 requests 发送 multipart/form-data
        files = [(key, (None, to_text(value))) for key, value in fields.items()]
        last_error = None
        for attempt in range(3):
            try:
                resp = self.session.post(url, files=files, timeout=self.timeout)
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.8 * (attempt + 1))
        else:
            self.use_curl = True
            try:
                return self.post_form_with_curl(url, fields)
            except Exception as curl_exc:
                raise RuntimeError("requests failed: {0}; curl fallback failed: {1}".format(last_error, curl_exc))
        try:
            # 解析 JSON 响应
            payload = resp.json()
        except ValueError:
            # 如果不是 JSON 响应，抛出错误
            raise RuntimeError(
                "Non-JSON response from {0}: HTTP {1} {2}".format(url, resp.status_code, resp.text[:300])
            )
        return payload

    def post_form_with_curl(self, url, fields):
        """
        使用 curl 命令发送 POST 表单请求（备用方案）。
        
        参数:
            url: 请求 URL
            fields: 表单字段字典
        
        返回:
            API 响应的 JSON 数据
        """
        # 生成唯一的文件名后缀（基于进程ID、时间戳和线程ID）
        suffix = "{0}_{1}_{2}".format(os.getpid(), int(time.time() * 1000), threading.current_thread().ident)
        config_path = os.path.abspath(".rakumart_curl_config_{0}.txt".format(suffix))  # curl 配置文件路径
        output_path = os.path.abspath(".rakumart_curl_output_{0}.json".format(suffix))  # 输出文件路径
        # 构建 curl 配置
        lines = [
            'url = "{0}"'.format(curl_escape(url)),  # 请求 URL
            'request = "POST"',  # 请求方法
            "silent",  # 静默模式
            "show-error",  # 显示错误
            "location",  # 跟随重定向
            'output = "{0}"'.format(curl_escape(output_path)),  # 输出文件
            'header = "User-Agent: RakumartBulkCart/1.0"',  # 用户代理头
            'header = "Accept: application/json, text/plain, */*"',  # 接受头
        ]
        # 如果存在 token，添加到请求头
        token = self.session.headers.get("clienttoken")
        if token:
            lines.append('header = "clienttoken: {0}"'.format(curl_escape(token)))
        # 添加表单字段
        for key, value in fields.items():
            lines.append('form-string = "{0}={1}"'.format(curl_escape(key), curl_escape(value)))

        # 写入 curl 配置文件
        with open(config_path, "wb") as f:
            f.write(b"\n".join(to_http_bytes(line) for line in lines) + b"\n")

        try:
            # 执行 curl 命令
            subprocess.check_call(["curl.exe", "--config", config_path])
            # 读取响应内容
            with open(output_path, "rb") as f:
                body = f.read()
        except OSError:
            # curl 未找到
            raise RuntimeError("curl.exe not found. Install requests for Python or ensure curl.exe is available.")
        except subprocess.CalledProcessError as exc:
            # curl 执行失败
            raise RuntimeError("curl request failed: {0}".format(exc))

        try:
            # 解析 JSON 响应
            return json.loads(body.decode("utf-8"))
        except Exception:
            # 如果不是 JSON 响应，抛出错误
            raise RuntimeError("Non-JSON response from {0}: {1}".format(url, body[:300]))
        finally:
            # 清理临时文件
            for path in (config_path, output_path):
                try:
                    os.remove(path)
                except Exception:
                    pass  # 删除失败则忽略

    def login(self, account, password, client_tool):
        """
        用户登录。
        
        参数:
            account: 账号
            password: 密码
            client_tool: 客户端类型（1=PC-WEB, 2=H5-WEB, 3=Android, 4=iOS）
        
        返回:
            登录成功后的 token
        """
        # 发送登录请求
        payload = self.post_form(
            "/client/userLogin",
            {
                "account": account,
                "password": password,
                "client_tool": client_tool,
            },
        )
        # 检查登录是否成功
        if not payload.get("success"):
            raise RuntimeError("Login failed: code={0} msg={1}".format(payload.get("code"), payload.get("msg")))

        # 提取 token
        data = payload.get("data") or {}
        token = data.get("userToken") if isinstance(data, dict) else ""
        if not token:
            raise RuntimeError("Login succeeded but userToken was missing: {0}".format(payload))

        # 将 token 添加到请求头（clienttoken）
        self.session.headers.update({"clienttoken": token})
        return token

    def search_goods(self, keyword, shop_type, page, page_size):
        """
        搜索商品。
        
        参数:
            keyword: 搜索关键词
            shop_type: 店铺类型（1688/taobao/tmall/rakumart）
            page: 页码
            page_size: 每页数量
        
        返回:
            API 响应数据
        """
        return self.post_form(
            "/client/searchGoods",
            {
                "keywords": keyword,
                "shop_type": shop_type,
                "page": page,
                "pageSize": page_size,
            },
        )

    def get_store_shop_id(self, keywords):
        """
        获取店铺信息。
        
        参数:
            keywords: 店铺链接或关键词
        
        返回:
            API 响应数据
        """
        return self.post_form("/client/getStoreShopId", {"keywords": keywords})

    def add_to_cart(self, items):
        """
        添加商品到购物车。
        
        参数:
            items: CartItem 列表
        
        返回:
            API 响应数据
        """
        fields = OrderedDict()  # 使用有序字典保持字段顺序
        for index, item in enumerate(items):
            prefix = "to_cart[{0}]".format(index)  # 构建字段前缀
            # 添加所有商品字段
            fields[prefix + "[goods_id]"] = item.goods_id
            fields[prefix + "[goods_title]"] = item.goods_title
            fields[prefix + "[price]"] = item.price
            fields[prefix + "[num]"] = item.num
            fields[prefix + "[pic]"] = item.pic
            fields[prefix + "[detail]"] = item.detail
            fields[prefix + "[sku_id]"] = item.sku_id
            fields[prefix + "[spec_id]"] = item.spec_id
            fields[prefix + "[shop_id]"] = item.shop_id
            fields[prefix + "[shop_name]"] = item.shop_name
            fields[prefix + "[from_platform]"] = item.from_platform
            fields[prefix + "[price_ranges]"] = item.price_ranges
            fields[prefix + "[trace]"] = item.trace
        return self.post_form("/client/cart.goodsToCart", fields)


def unwrap_goods_list(payload):
    """
    从搜索响应中提取商品列表。
    
    参数:
        payload: API 响应数据
    
    返回:
        商品字典列表
    """
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return []  # 如果不是字典，返回空列表

    result = data.get("result")
    if isinstance(result, dict):
        # 尝试多种可能的字段名获取商品列表
        goods = result.get("result") or result.get("list") or result.get("data")
        return [x for x in as_list(goods) if isinstance(x, dict)]
    return [x for x in as_list(result) if isinstance(x, dict)]


def unwrap_goods_detail(payload):
    """
    从商品详情响应中提取详情数据。
    
    参数:
        payload: API 响应数据
    
    返回:
        商品详情字典
    """
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return {}  # 如果不是字典，返回空字典
    result = data.get("result")
    return result if isinstance(result, dict) else {}


def normalize_shop(raw):
    """
    从原始数据中提取店铺信息。
    
    参数:
        raw: 包含店铺信息的字典
    
    返回:
        (shop_id, shop_name, shop_url) 元组
    """
    # 尝试多种可能的字段名获取店铺ID
    shop_id = to_text(
        pick(
            raw,
            "shop_id",
            "shopId",
            "shopID",
            "sellerId",
            "seller_id",
            "sellerUserId",
            "memberId",
        )
    )
    # 尝试多种可能的字段名获取店铺名称
    shop_name = to_text(
        pick(
            raw,
            "shop_name",
            "shopName",
            "sellerName",
            "sellerNick",
            "companyName",
            "wangName",
            "nick",
        )
    )
    # 尝试多种可能的字段名获取店铺URL
    shop_url = to_text(pick(raw, "shopUrl", "shop_url", "sellerUrl", "storeUrl", "url"))
    return shop_id, shop_name, shop_url


def enrich_shop_from_url(client, raw):
    """
    通过店铺URL获取并补充店铺信息。
    
    参数:
        client: RakumartClient 实例
        raw: 包含商品信息的字典
    """
    shop_id, _shop_name, shop_url = normalize_shop(raw)
    if shop_id or not shop_url:
        return  # 如果已有店铺ID或没有URL，则跳过
    # 调用 API 获取店铺信息
    payload = client.get_store_shop_id(shop_url)
    if not payload.get("success"):
        return  # 获取失败则跳过
    data = payload.get("data") or {}
    if isinstance(data, dict):
        # 补充店铺信息到原始数据
        raw.setdefault("shop_id", data.get("shop_id") or "")
        raw.setdefault("shopName", data.get("shopName") or "")
        raw.setdefault("wangName", data.get("wangName") or "")


def extract_specs(raw):
    """
    从商品数据中提取规格列表。
    
    参数:
        raw: 商品数据字典
    
    返回:
        规格字典列表
    """
    candidates = []  # 候选规格列表
    # 尝试多种可能的字段名获取规格列表
    for key in (
        "skuList",
        "sku_list",
        "skus",
        "skuInfos",
        "skuInfo",
        "specs",
        "specList",
        "skuMap",
        "sku",
    ):
        candidates.extend(as_list(raw.get(key)))

    # 从 goodsInfo 中提取规格
    goods_info = raw.get("goodsInfo") or {}
    if isinstance(goods_info, dict):
        candidates.extend(as_list(goods_info.get("skuList")))
        candidates.extend(as_list(goods_info.get("skus")))

        # 从库存信息中提取规格
        for inv in as_list(goods_info.get("goodsInventory")):
            if not isinstance(inv, dict):
                continue
            # 获取规格名称
            spec_name = to_text(pick(inv, "keyC", "keyT", "name", {"default": "默认规格"}))
            # 获取规格值列表
            values = as_list(inv.get("valueC") or inv.get("valueT") or inv.get("values"))
            if not values:
                values = [inv]
            for value in values:
                if not isinstance(value, dict):
                    continue
                # 检查库存是否充足
                amount = value.get("amountOnSale")
                if amount not in (None, "") and parse_int(amount, 1) <= 0:
                    continue  # 库存不足则跳过
                spec = dict(value)  # 复制规格数据
                spec.setdefault("name", spec_name)  # 设置规格名称
                spec.setdefault("detail", [{"key": "规格", "value": spec_name}])  # 设置规格详情
                candidates.append(spec)
    return [x for x in candidates if isinstance(x, dict)]  # 过滤非字典项


def extract_price_ranges(raw, default_price):
    """
    从商品数据中提取价格区间。
    
    参数:
        raw: 商品数据字典
        default_price: 默认价格
    
    返回:
        价格区间列表
    """
    goods_info = raw.get("goodsInfo") or {}
    # 尝试多种可能的字段名获取价格区间
    price_ranges = pick(
        raw,
        "price_ranges",
        "priceRanges",
        "priceRange",
        {"default": None},
    )
    if not price_ranges and isinstance(goods_info, dict):
        price_ranges = pick(goods_info, "price_ranges", "priceRanges", "priceRange", {"default": None})
    if not price_ranges:
        # 如果没有价格区间，使用默认价格
        price_ranges = [{"priceMin": default_price, "priceMax": default_price, "startQuantity": 1}]
    return price_ranges


def first_image(raw):
    """
    从商品数据中获取第一张图片URL。
    
    参数:
        raw: 商品数据字典
    
    返回:
        图片URL字符串
    """
    # 尝试多种可能的字段名获取图片URL
    pic = to_text(pick(raw, "imgUrl", "pic", "image", "mainPic", "mainImage", "picUrl"))
    if pic:
        return pic
    # 尝试从图片列表中获取
    images = as_list(raw.get("images"))
    for image in images:
        if image:
            return to_text(image)
    return ""  # 没有找到则返回空字符串


def base_price(raw):
    """
    从商品数据中获取基础价格。
    
    参数:
        raw: 商品数据字典
    
    返回:
        价格字符串
    """
    # 尝试多种可能的字段名获取价格
    price = to_text(pick(raw, "goodsPrice", "price", "priceMin", "salePrice", {"default": ""}))
    if price:
        return price
    # 从价格区间中获取
    ranges = extract_price_ranges(raw, "0")
    if isinstance(ranges, list) and ranges and isinstance(ranges[0], dict):
        return to_text(pick(ranges[0], "priceMin", "priceMax", {"default": "0"}))
    return "0"


def detail_url_for_goods(raw, shop_type):
    """
    获取商品详情页URL。
    
    参数:
        raw: 商品数据字典
        shop_type: 店铺类型
    
    返回:
        商品详情页URL
    """
    # 尝试多种可能的字段名获取URL
    url = to_text(pick(raw, "fromUrl", "goodsUrl", "detailUrl", "itemUrl", "url", "goodsUrlMobile"))
    if url and url.startswith("http"):
        return url  # 如果已有完整URL，直接返回
    # 根据商品ID和平台构建URL
    goods_id = to_text(pick(raw, "goodsId", "goods_id", "offerId", "offer_id", "itemId", "id"))
    platform = to_text(pick(raw, "shopType", "fromPlatform", "from_platform", {"default": shop_type or "1688"}))
    if goods_id and platform.lower() == "1688":
        return "https://detail.1688.com/offer/{0}.html".format(goods_id)
    return ""  # 无法构建则返回空字符串


def fetch_goods_detail(client, raw, shop_type, detail_cache):
    """
    获取商品详情。
    
    参数:
        client: RakumartClient 实例
        raw: 商品基础数据
        shop_type: 店铺类型
        detail_cache: 详情缓存字典
    
    返回:
        商品详情数据
    """
    # 如果已有店铺ID和规格信息，直接返回
    if normalize_shop(raw)[0] and extract_specs(raw):
        return raw

    goods_id = to_text(pick(raw, "goodsId", "goods_id", "offerId", "offer_id", "itemId", "id"))
    if goods_id in detail_cache:
        return detail_cache[goods_id]  # 从缓存中获取

    detail_url = detail_url_for_goods(raw, shop_type)
    if not detail_url:
        detail_cache[goods_id] = raw  # 缓存并返回原始数据
        return raw

    platform = to_text(pick(raw, "shopType", "fromPlatform", "from_platform", {"default": shop_type or "1688"}))
    # 通过搜索接口获取商品详情（使用商品链接作为关键词）
    payload = client.search_goods(detail_url, platform, 1, 1)
    if payload.get("success"):
        detail = unwrap_goods_detail(payload)
        if detail:
            # 保留原始数据中的某些字段
            for key in ("goodsPrice", "imgUrl", "sales"):
                if key in raw and key not in detail:
                    detail[key] = raw.get(key)
            detail_cache[goods_id] = detail  # 缓存详情
            return detail

    log("[WARN] detail fetch failed goods_id={0} msg={1}".format(goods_id, payload.get("msg")))
    detail_cache[goods_id] = raw  # 缓存原始数据
    return raw


def build_cart_candidates(raw, client, quantity_cycle, allow_fallback_sku):
    """
    构建购物车候选商品列表。
    
    参数:
        raw: 商品数据
        client: RakumartClient 实例
        quantity_cycle: 数量循环列表
        allow_fallback_sku: 是否允许使用默认SKU
    
    返回:
        CartItem 列表
    """
    enrich_shop_from_url(client, raw)  # 补充店铺信息

    # 提取商品基本信息
    goods_id = to_text(pick(raw, "goodsId", "goods_id", "offerId", "offer_id", "itemId", "id"))
    title = to_text(pick(raw, "titleC", "titleT", "title", "goodsTitle", "name"))
    price = base_price(raw)
    pic = first_image(raw)
    from_platform = to_text(pick(raw, "shopType", "fromPlatform", "from_platform", "platform", {"default": "1688"}))
    shop_id, shop_name, _shop_url = normalize_shop(raw)

    # 检查必要字段
    if not goods_id or not title:
        return []  # 缺少必要字段，返回空列表

    # 如果没有店铺ID，使用店铺名称作为兜底
    if not shop_id:
        shop_id = shop_name
    if not shop_name:
        shop_name = shop_id or "未知店铺"
    if not shop_id:
        return []  # 仍然没有店铺ID，返回空列表

    specs = extract_specs(raw)  # 提取规格列表
    items = []

    if specs:
        # 有规格信息，为每个规格创建一个购物车项
        for i, spec in enumerate(specs):
            sku_id = to_text(pick(spec, "sku_id", "skuId", "skuID", "id"))
            spec_id = to_text(pick(spec, "spec_id", "specId", "specID", "id"))
            spec_price = to_text(pick(spec, "price", "priceMin", "salePrice", {"default": price}))
            detail = pick(spec, "detail", "attrs", "attributes", "properties", "specAttrs", {"default": None})
            if not detail:
                # 如果没有规格详情，构建默认详情
                name = pick(spec, "name", "specName", "value", "skuName", {"default": "规格{0}".format(i + 1)})
                detail = [{"key": "规格", "value": to_text(name)}]
            price_ranges = extract_price_ranges(raw, spec_price)
            start_quantity = parse_int(pick(spec, "startQuantity", "start_quantity", {"default": 1}), 1)
            # 创建购物车项
            items.append(
                CartItem(
                    goods_id=goods_id,
                    goods_title=title,
                    price=spec_price,
                    num=max(quantity_cycle[i % len(quantity_cycle)], start_quantity),  # 使用数量循环
                    pic=pic,
                    detail=json_text(detail),
                    sku_id=sku_id or spec_id or goods_id,
                    spec_id=spec_id or sku_id or goods_id,
                    shop_id=shop_id,
                    shop_name=shop_name,
                    from_platform=from_platform,
                    price_ranges=json_text(price_ranges),
                    trace="bulk-{0}-{1}".format(goods_id, i),  # 追踪标识
                )
            )
    elif allow_fallback_sku:
        # 没有规格信息，使用默认SKU
        price_ranges = extract_price_ranges(raw, price)
        items.append(
            CartItem(
                goods_id=goods_id,
                goods_title=title,
                price=price,
                num=quantity_cycle[0],
                pic=pic,
                detail=json_text([{"key": "规格", "value": "默认"}]),
                sku_id=to_text(pick(raw, "sku_id", "skuId", "skuID", {"default": goods_id})),
                spec_id=to_text(pick(raw, "spec_id", "specId", "specID", {"default": goods_id})),
                shop_id=shop_id,
                shop_name=shop_name,
                from_platform=from_platform,
                price_ranges=json_text(price_ranges),
                trace="bulk-{0}-fallback".format(goods_id),
            )
        )

    return items


def unique_append(existing, candidates, limit):
    """
    将候选商品添加到现有列表，避免重复，直到达到限制数量。
    
    参数:
        existing: 现有购物车项列表
        candidates: 候选购物车项列表
        limit: 限制数量
    """
    # 记录已存在的商品标识（goods_id, sku_id, spec_id）
    seen = set((x.goods_id, x.sku_id, x.spec_id) for x in existing)
    for item in candidates:
        key = (item.goods_id, item.sku_id, item.spec_id)
        if key in seen:
            continue  # 跳过重复项
        existing.append(item)
        seen.add(key)
        if len(existing) >= limit:
            break  # 达到限制数量，停止添加


def collect_items(
    client,
    keyword,
    shop_type,
    target_shops,
    per_shop,
    page_size,
    max_pages,
    sleep_seconds,
    quantity_cycle,
    allow_fallback_sku,
    detail_workers,
):
    """
    收集商品并分组到各个店铺。
    
    参数:
        client: RakumartClient 实例
        keyword: 搜索关键词
        shop_type: 店铺类型
        target_shops: 目标店铺数量
        per_shop: 每个店铺的商品数量
        page_size: 每页搜索结果数量
        max_pages: 最大搜索页数
        sleep_seconds: 每页之间的休眠时间（秒）
        quantity_cycle: 数量循环列表
        allow_fallback_sku: 是否允许使用默认SKU
        detail_workers: 并行获取详情的线程数
    
    返回:
        按店铺分组的商品字典
    """
    shops = OrderedDict()  # 使用有序字典保持店铺顺序
    detail_cache = {}  # 商品详情缓存

    # 逐页搜索商品
    for page in range(1, max_pages + 1):
        payload = client.search_goods(keyword, shop_type, page, page_size)
        if not payload.get("success"):
            log("[WARN] search page={0} failed: code={1} msg={2}".format(page, payload.get("code"), payload.get("msg")))
            break  # 搜索失败，停止

        goods = unwrap_goods_list(payload)  # 提取商品列表
        ready = sum(1 for v in shops.values() if len(v) >= per_shop)  # 计算已就绪的店铺数
        log("[INFO] page={0} goods={1} shops_ready={2}/{3}".format(page, len(goods), ready, target_shops))
        if not goods:
            break  # 没有商品，停止

        def load_detail(raw):
            """加载商品详情的内部函数"""
            try:
                return fetch_goods_detail(client, raw, shop_type, detail_cache)
            except Exception as exc:
                goods_id = to_text(pick(raw, "goodsId", "goods_id", "offerId", "offer_id", "itemId", "id"))
                log("[WARN] detail exception goods_id={0}: {1}".format(goods_id, exc))
                return raw

        # 并行或串行获取商品详情
        if detail_workers > 1 and ThreadPool is not None and len(goods) > 1:
            pool = ThreadPool(detail_workers)
            try:
                detailed_goods = pool.map(load_detail, goods)
            finally:
                pool.close()
                pool.join()
        else:
            detailed_goods = [load_detail(raw) for raw in goods]

        # 将商品按店铺分组
        for raw in detailed_goods:
            candidates = build_cart_candidates(raw, client, quantity_cycle, allow_fallback_sku)
            if not candidates:
                continue  # 没有候选商品，跳过
            shop_key = candidates[0].shop_id or candidates[0].shop_name
            if not shop_key:
                continue  # 没有店铺标识，跳过
            bucket = shops.setdefault(shop_key, [])  # 获取或创建店铺桶
            if len(bucket) < per_shop:
                unique_append(bucket, candidates, per_shop)  # 添加不重复的商品

        # 检查是否已达到目标店铺数
        ready = sum(1 for items in shops.values() if len(items) >= per_shop)
        log("[INFO] page={0} done shops_ready={1}/{2} detail_cache={3}".format(page, ready, target_shops, len(detail_cache)))
        if ready >= target_shops:
            break  # 已达到目标，停止搜索
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)  # 休眠一段时间

    return shops


def flatten_ready_shops(shops, target_shops, per_shop):
    """
    将准备好的店铺商品展平为列表。
    
    参数:
        shops: 按店铺分组的商品字典
        target_shops: 目标店铺数量
        per_shop: 每个店铺的商品数量
    
    返回:
        CartItem 列表
    """
    selected = []
    ready_count = 0
    for items in shops.values():
        if len(items) < per_shop:
            continue  # 跳过商品不足的店铺
        selected.extend(items[:per_shop])  # 取前 per_shop 个商品
        ready_count += 1
        if ready_count >= target_shops:
            break  # 已达到目标店铺数
    return selected


def chunks(items, size):
    """
    将列表分块。
    
    参数:
        items: 要分块的列表
        size: 每块大小
    
    返回:
        分块后的生成器
    """
    for i in range(0, len(items), size):
        yield items[i : i + size]  # 返回每个块


def parse_args():
    """
    解析命令行参数。
    
    返回:
        解析后的参数对象
    """
    parser = argparse.ArgumentParser(description="Search clothes and add 3 items/specs from each shop to Rakumart cart.")
    parser.add_argument("--account", default=os.getenv("RAKUMART_ACCOUNT", ""), help="Rakumart 账号")
    parser.add_argument("--password", default=os.getenv("RAKUMART_PASSWORD", ""), help="Rakumart 密码")
    parser.add_argument("--client-tool", default="1", help="1=PC-WEB, 2=H5-WEB, 3=Android, 4=iOS")
    parser.add_argument("--keyword", default="衣服", help="搜索关键词")
    parser.add_argument("--shop-type", default="1688", help="1688/taobao/tmall/rakumart")
    parser.add_argument("--target-shops", type=int, default=100, help="达到此店铺数后停止")
    parser.add_argument("--per-shop", type=int, default=3, help="每个店铺的商品/规格数")
    parser.add_argument("--page-size", type=int, default=50, help="搜索每页数量")
    parser.add_argument("--max-pages", type=int, default=80, help="最大搜索页数")
    parser.add_argument("--batch-size", type=int, default=30, help="每次请求添加的购物车项数")
    parser.add_argument("--sleep", type=float, default=0.2, help="每页/批次之间的休眠秒数")
    parser.add_argument("--detail-workers", type=int, default=4, help="获取商品详情的并行线程数")
    parser.add_argument("--quantities", default="2,3,5", help="3个商品/规格的数量循环，如 2,3,5")
    parser.add_argument("--no-fallback-sku", action="store_true", help="没有sku/spec时跳过，而不是使用goodsId兜底")
    parser.add_argument("--execute", action="store_true", help="真正添加到购物车。不加此参数只写入预览JSON。")
    parser.add_argument("--preview-file", default="rakumart_cart_preview.json", help="预演模式输出文件")
    return parser.parse_args()


def main():
    """
    主函数。
    
    返回:
        退出码（0=成功，1=错误，2=参数缺失）
    """
    args = parse_args()  # 解析命令行参数
    if not args.account or not args.password:
        print("Missing account/password. Use --account/--password or set RAKUMART_ACCOUNT/RAKUMART_PASSWORD.", file=sys.stderr)
        return 2  # 缺少必要参数

    # 解析数量循环列表
    quantities = [int(x.strip()) for x in args.quantities.split(",") if x.strip()]
    if not quantities:
        quantities = [1]  # 默认数量为1

    client = RakumartClient(BASE_URL, 25)  # 创建客户端，超时25秒
    log("[INFO] logging in...")
    client.login(args.account, args.password, args.client_tool)  # 登录
    log("[INFO] login ok; token is set to request header: clienttoken")

    # 收集商品
    shops = collect_items(
        client=client,
        keyword=args.keyword,
        shop_type=args.shop_type,
        target_shops=args.target_shops,
        per_shop=args.per_shop,
        page_size=args.page_size,
        max_pages=args.max_pages,
        sleep_seconds=args.sleep,
        quantity_cycle=quantities,
        allow_fallback_sku=not args.no_fallback_sku,
        detail_workers=max(1, args.detail_workers),
    )
    items = flatten_ready_shops(shops, args.target_shops, args.per_shop)  # 展平商品列表
    ready_shops = len(items) // args.per_shop  # 计算就绪店铺数
    log("[INFO] collected ready shops={0}, cart items={1}".format(ready_shops, len(items)))

    # 如果店铺数不足，发出警告
    if ready_shops < args.target_shops:
        log("[WARN] only {0}/{1} shops have {2} usable items/specs.".format(ready_shops, args.target_shops, args.per_shop))

    # 如果不是执行模式，只写入预览文件
    if not args.execute:
        with open(args.preview_file, "w") as f:
            data = json_ready([item.to_dict() for item in items])
            text = json.dumps(data, ensure_ascii=False, indent=2)
            if not isinstance(text, str):
                text = text.encode("utf-8")
            f.write(text)
        log("[DRY-RUN] preview written to {0}".format(args.preview_file))
        log("[DRY-RUN] add --execute to really add these items to cart.")
        return 0  # 预演模式完成

    # 执行模式：真正添加到购物车
    if not items:
        log("[ERROR] no items to add.", error=True)
        return 1  # 没有商品可添加

    log("[INFO] adding to cart...")
    success_batches = 0  # 成功批次计数
    for batch_index, batch in enumerate(chunks(items, args.batch_size), start=1):
        payload = client.add_to_cart(batch)  # 添加一批商品到购物车
        ok = bool(payload.get("success")) and payload.get("code") == 0  # 检查是否成功
        log(
            "[INFO] batch={0} size={1} ok={2} code={3} msg={4}".format(
                batch_index, len(batch), ok, payload.get("code"), payload.get("msg")
            )
        )
        if ok:
            success_batches += 1  # 成功批次加1
        else:
            log(json.dumps(payload, ensure_ascii=False, indent=2))  # 打印错误详情
        if args.sleep > 0:
            time.sleep(args.sleep)  # 批次间休眠

    log("[DONE] success_batches={0}".format(success_batches))
    return 0  # 执行完成


if __name__ == "__main__":
    sys.exit(main())  # 运行主函数并退出


"""
========================================
运行命令示例（在命令行中执行）
========================================

先进入文件所在目录：
   cd d:\python__jiaoben

1. 预演模式（只生成预览文件，不真正添加购物车）
   py piliangtianjiagouwuche.py --account 12345678990 --password 123456 --keyword 衣服

2. 真正执行添加购物车
   py piliangtianjiagouwuche.py --account 12345678990 --password 123456 --keyword 衣服 --execute

3. 修改目标店铺数为 5 个
   py piliangtianjiagouwuche.py --account 12345678990 --password 123456 --keyword 衣服 --target-shops 5 --execute

4. 修改每店商品数为 2 个
   py piliangtianjiagouwuche.py --account 12345678990 --password 123456 --keyword 衣服 --per-shop 2 --execute

5. 修改搜索关键词为 "鞋子"
   py piliangtianjiagouwuche.py --account 12345678990 --password 123456 --keyword 鞋子 --execute

常用参数说明：
  --account       账号（默认从环境变量 RAKUMART_ACCOUNT 读取）
  --password      密码（默认从环境变量 RAKUMART_PASSWORD 读取）
  --keyword       搜索关键词（默认：衣服）
  --shop-type     店铺类型：1688/taobao/tmall/rakumart（默认：1688）
  --target-shops  目标店铺数量（默认：10）
  --per-shop      每个店铺添加的商品数量（默认：3）
  --execute       真正执行添加（不加则只预览）
  --max-pages     最大搜索页数（默认：80）
  --sleep         每页/批次间隔秒数（默认：0.2）
"""
