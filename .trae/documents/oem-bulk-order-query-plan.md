# OEM 大货单查询报价脚本 — 实现计划

## 摘要

创建 `run_oem_bulk_order_query_script` 脚本函数：输入询价单号，查询完整报价信息（样品/大货单价、SKU明细、工厂信息等），为后续下大货单做准备。

## 当前状态分析

- [app/data_scripts.py](file:///d:/A_zidonghuapingtai/app/data_scripts.py) 中已有 `fetch_oem_full_quote`（L8940），实现两步查询：
  1. `POST /api/inquiryDetail` → 获取 detail_id 及工厂信息
  2. `POST /api/quoteDetail` → 获取完整报价明细（含 `samples_info`、`large_info`、SKU 明细）
- 该函数已在 [app/routers/data_scripts.py](file:///d:/A_zidonghuapingtai/app/routers/data_scripts.py) L437 注册为 GET `/oem/inquiry-full`，但缺少标准脚本封装（无 log/steps 追踪、无变量体系集成）
- 现有脚本模式：`run_oem_sample_full_flow_script`（L9557）是标准参考，使用 `_step`、`_finish_named`、`_oem_client_login` 等 helper

## 改动文件清单

### 1. [app/data_scripts.py](file:///d:/A_zidonghuapingtai/app/data_scripts.py) — 新增脚本函数

**位置**: 在 `run_oem_sample_full_flow_script` 之后（约 L9850），新增：

```python
OEM_BULK_ORDER_QUERY_NAME = "OEM大货单查询报价"

def run_oem_bulk_order_query_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 大货单查询报价脚本：输入询价单号 → 查询完整报价信息。
    
    两步查询：
      1. POST /api/inquiryDetail → 获取 detail_id 及工厂信息
      2. POST /api/quoteDetail  → 获取完整报价明细（样品/大货/SKU）
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")
    order_sn = str(variables.get("order_sn") or "").strip()

    log: Dict[str, Any] = {
        "script": OEM_BULK_ORDER_QUERY_NAME,
        "mode": "oem_bulk_order_query",
        "base_url": base_url,
        "order_sn": order_sn,
        "started_at": datetime.now(),
        "steps": [],
    }

    if not order_sn:
        return _finish_named(OEM_BULK_ORDER_QUERY_NAME, log, False,
                             {"reason": "缺少必填参数：询价单号 order_sn 不能为空"})

    try:
        quote_data = fetch_oem_full_quote(order_sn, variables)
        if not quote_data:
            return _finish_named(OEM_BULK_ORDER_QUERY_NAME, log, False,
                                 {"reason": f"查询报价失败：询价单 {order_sn} 无报价数据或接口返回异常"})

        # 提取关键信息
        quote_detail = quote_data.get("quote_detail") or {}
        samples_info = quote_detail.get("samples_info") or {}
        large_info = quote_detail.get("large_info") or {}
        detail_list = quote_data.get("detail_list") or quote_data.get("list") or []

        _step(log, "query_quote", {"order_sn": order_sn},
              {"url": "/api/inquiryDetail + /api/quoteDetail", "method": "POST"},
              {"detail_id": quote_data.get("detail_id"),
               "factory_count": len(detail_list),
               "has_samples": bool(samples_info),
               "has_large": bool(large_info)})

        summary = {
            "order_sn": order_sn,
            "detail_id": quote_data.get("detail_id"),
            "goods_name": quote_data.get("goods_name") or "",
            "factory_count": len(detail_list),
            "samples_info": samples_info,
            "large_info": large_info,
            "quote_data": quote_data,
            "reason": "查询报价成功",
        }
        return _finish_named(OEM_BULK_ORDER_QUERY_NAME, log, True, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_BULK_ORDER_QUERY_NAME, log, False,
                             {"reason": str(exc), "error": str(exc)})
```

### 2. [app/routers/data_scripts.py](file:///d:/A_zidonghuapingtai/app/routers/data_scripts.py) — 注册路由

**位置**: 在 `run_oem_sample_full_flow_data_script` 之后（约 L419），新增：

```python
@router.post("/data-scripts/oem-bulk-order-query")
def run_oem_bulk_order_query_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func(
        "run_oem_bulk_order_query_script", run_oem_bulk_order_query_script
    )(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data
```

**同时**: 在文件顶部 import 中添加 `run_oem_bulk_order_query_script`（约 L46）。

### 3. [app/core/utils.py](file:///d:/A_zidonghuapingtai/app/core/utils.py) — 注册 API Case

在 `OEM_DATA_SCRIPT_API_CASES` 列表（L757）末尾追加：

```python
{
    "key": "oem_bulk_order_query",
    "case_name": "OEM-大货单查询报价",
    "url": "/api/inquiryDetail",
    "body": {"order_sn": "{{order_sn}}"},
},
```

### 4. [static/app.js](file:///d:/A_zidonghuapingtai/static/app.js) — 前端集成

**4a. 脚本类型定义**（约 L8 附近，`SCRIPT_TYPES` 中追加）：
```javascript
oem_bulk_order_query: { id: "oem_bulk_order_query_builtin", name: "OEM大货单查询报价" },
```

**4b. 参数 Schema**（约 L60 附近，`SCRIPT_PARAM_SCHEMAS` 中追加）：
```javascript
oem_bulk_order_query: [
    { name: "__section_account", type: "section", label: "登录信息" },
    { name: "account", label: "前台账号", default: "12345678990" },
    { name: "password", label: "前台密码", default: "123456" },
    { name: "__section_query", type: "section", label: "查询参数" },
    { name: "order_sn", label: "询价单号", required: true },
],
```

**4c. 流程注册**（参考 `oem_sample_full_flow` 模式，约 L855 附近新增类似函数）：
```javascript
function ensureOemBulkOrderQueryFlow(flows, projectId, envId) {
  if (isBuiltinDeleted("oem_bulk_order_query_builtin")) return flows;
  // ... 同 oem_sample_full_flow 模式
}
```

**4d. 执行处理**（约 L640 附近新增）：
```javascript
if (flow.scriptType === "oem_bulk_order_query") {
  progress.update(24, "正在执行OEM大货单查询报价...");
  // ... POST /data-scripts/oem-bulk-order-query
}
```

**4e. `builtInTypes` 列表中追加** `"oem_bulk_order_query"`（约 L1746）。

## 假设与决策

- 使用前台 token（`/api/login`）查询报价，与 `fetch_oem_full_quote` 一致
- 脚本名称为 `"OEM大货单查询报价"`，后续大货单下单脚本在此基础上扩展
- 返回的 `summary` 中包含完整 `quote_data`，供后续下大货单步骤使用
- 前端参数只保留最小必要字段（order_sn + 登录信息），后续下单步骤再扩展

## 验证步骤

1. 在 OEM 项目环境中，通过前端执行该脚本，输入一个已有报价的询价单号
2. 确认返回的 `summary` 中包含 `samples_info`、`large_info`、`detail_id` 等字段
3. 确认执行记录正确保存到数据库
4. 确认无报价的询价单号能正确返回失败信息