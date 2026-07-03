# OEM 询价单全流程 - 修复 factory_iid 从 factory_url 解析 memberId

## 背景

当前 OEM 询价单全流程脚本在 `factoryEdit` 和 `factoryQuote` 调用时，`factory_iid` 字段依赖后端 `detail_list` 返回，兜底是空字符串 `""`。但：

1. 创建询价单 `/api/newInquiry` 时只传 `factory_urls`（URL 字符串数组），**不传 factory_iid**
2. 后端 `detail_list` 可能不填充 `factory_iid`（或返回空）
3. 脚本**完全没有**从 `factory_url` 解析 `memberId` 的逻辑
4. 导致 `factoryEdit` 虽然成功（后端容忍空 factory_iid），但后续 `factoryQuote` 报"参数错误"（allure 日志佐证）

用户提供的 curl 显示正确的 `factory_iid` 取值方式：从 `factory_url` 的 `memberId` 参数解析。

**示例**：
```
factory_url = https://sale.1688.com/factory/card.html?spm=...&memberId=b2b-2216921663537497f8&aHdkaW5n_isCentral=true&...
→ factory_iid = b2b-2216921663537497f8
```

## 当前实现分析

### `app/data_scripts.py` 阶段3（行 9202-9230）

```python
for idx, d_item in enumerate(detail_list):
    detail_id = d_item.get("id")
    factory_url = d_item.get("factory_url") or ""
    factory_submit_info = d_item.get("factory_submit_info") or factory_url
    factory_iid = d_item.get("factory_iid") or ""          # ← 问题：兜底空字符串
    factory_name = d_item.get("factory_name") or "测试工厂"
    ...
    edit_body: Dict[str, Any] = {
        "detail_id": detail_id,
        "factory_iid": factory_iid,                         # ← 传空字符串给后端
        ...
    }
```

### `_oem_parse_factory_urls`（行 8580-8590）

```python
def _oem_parse_factory_urls(variables: Dict[str, Any]) -> list:
    raw = variables.get("factory_urls")
    if raw and isinstance(raw, list):
        return raw
    if raw and isinstance(raw, str):
        urls = [line.strip() for line in raw.splitlines() if line.strip()]
        if urls:
            return urls
    old = variables.get("factory_url")
    return [old] if old else []
```

只返回 URL 字符串列表，**不解析 memberId**。

### `memberId` 关键字

`app/data_scripts.py` 全文搜索 `memberId` **无任何匹配**。当前脚本完全不知道 1688 URL 里有 memberId 参数。

## 提议改动

### 改动1：新增 `_oem_extract_factory_iid` 工具函数

**位置**：`app/data_scripts.py`，紧邻 `_oem_parse_factory_urls` 函数后（约第 8591 行）

**作用**：从 1688 工厂链接解析 `memberId` 参数值作为 `factory_iid`

**实现**：
```python
def _oem_extract_factory_iid(factory_url: str) -> str:
    """从 1688 工厂链接解析 memberId 作为 factory_iid。

    支持格式：
    - https://sale.1688.com/factory/card.html?...&memberId=b2b-2216921663537497f8&...
    - https://detail.1688.com/offer/xxx.html?memberId=b2b-xxx
    - 其他含 memberId= 参数的 URL

    若 URL 不含 memberId 参数，返回空字符串。
    """
    if not factory_url:
        return ""
    import re
    # 匹配 memberId=xxx 参数值（直到 & 或 # 或行尾）
    m = re.search(r'[?&]memberId=([^&#\s]+)', factory_url)
    return m.group(1) if m else ""
```

**正则说明**：
- `[?&]memberId=` 匹配 `?memberId=` 或 `&memberId=`
- `([^&#\s]+)` 捕获到下一个 `&` / `#` / 空白为止的值
- 不匹配时返回空字符串（保持向后兼容）

### 改动2：阶段3 循环内 factory_iid 兜底解析

**位置**：`app/data_scripts.py` 阶段3 循环内（约第 9206 行）

**改动**：当后端 `d_item.get("factory_iid")` 为空时，从 `factory_url` 解析 memberId 兜底

```python
# 改前
factory_iid = d_item.get("factory_iid") or ""

# 改后
factory_iid = d_item.get("factory_iid") or _oem_extract_factory_iid(factory_url)
```

**为什么这样改**：
- 后端返回了 factory_iid 时优先用后端值（向后兼容）
- 后端没返回时从 factory_url 解析 memberId（修复 factory_iid 为空导致 factoryQuote 报错）
- 不破坏现有任何流程

### 改动3：不改动其他字段

根据用户提供的 curl，`factory_name` 和 `salesman` 字段后端接受空值（curl 里是 `"  "` 空格），`salesman_phone` 和 `factory_img` 当前全局取值即可。因此：

- `factory_name`：保持 `"测试工厂"` 兜底（不影响流程）
- `salesman` / `salesman_phone` / `factory_img`：保持全局 variables 取值
- `_oem_parse_factory_urls`：不改（保持返回 URL 字符串列表）
- 前端 schema：不改
- `app/core/utils.py` 用例模板：不改

## 不改动

- `static/app.js`（前端无变化）
- `app/core/utils.py`（用例模板不变）
- `app/routers/data_scripts.py`（路由不变）
- `_oem_parse_factory_urls`（保持原逻辑）
- factory_name / salesman / salesman_phone / factory_img 字段取值逻辑

## 假设与决策

1. **factory_iid 来源优先级**：后端 `d_item.factory_iid` > 从 `factory_url` 解析 `memberId` > 空字符串
2. **正则覆盖范围**：1688 工厂链接格式 `https://sale.1688.com/factory/card.html?...&memberId=b2b-xxx&...`，也兼容 `https://detail.1688.com/offer/xxx.html?memberId=b2b-xxx`
3. **非 1688 URL**：若 URL 不含 memberId 参数（如 `https://shop1.1688.com`），解析返回空字符串，不报错，保持现状
4. **最小改动**：只新增 1 个工具函数 + 1 行兜底逻辑，不涉及前端和其他字段

## 验证步骤

1. **单元验证**：用用户提供的 curl URL 测试 `_oem_extract_factory_iid`：
   ```
   URL = https://sale.1688.com/factory/card.html?spm=a260k.22464671.llq7jdxw.25.7e847a6eplJjaR&memberId=b2b-2216921663537497f8&aHdkaW5n_isCentral=true&...
   期望: b2b-2216921663537497f8
   ```
2. **全流程自测**：跑 `run_oem_full_inquiry_flow_script`，2 工厂，验证：
   - factoryEdit 步骤的 edit_body 里 `factory_iid` 不再是空字符串
   - factoryQuote 步骤不再报"参数错误"
   - 全流程 passed=True
3. **向后兼容**：旧 variables（无 factory_urls 变化）跑全流程，行为不变
4. **git commit**：自测通过后提交

## 文件清单

- `app/data_scripts.py`（新增 `_oem_extract_factory_iid` 函数 + 阶段3 factory_iid 兜底解析 1 行）
