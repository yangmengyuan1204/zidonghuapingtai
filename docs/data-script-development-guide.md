# 数据脚本开发规范

本文档用于规范后续新增、修改、注册数据脚本，目标是避免 `app/data_scripts/__init__.py` 再次膨胀，同时保证已有脚本、接口和数据不受影响。

## 核心原则

- 新脚本默认按业务域放入子模块，不允许继续直接塞进 `app/data_scripts/__init__.py`。
- `app/data_scripts/__init__.py` 只作为兼容导出层，负责导出旧调用方需要的入口。
- 修改数据脚本时，只允许改当前目标脚本；不得顺手修改其他已有脚本逻辑。
- 不得改变已有脚本的入参、返回值、注册 key、接口路径和执行流程。
- 不做数据库迁移、不删除业务数据、不修改真实报告和运行日志，除非需求明确要求。

## 推荐目录结构

```text
app/data_scripts/
  __init__.py          # 兼容导出，不写新业务逻辑
  registry.py          # SCRIPT_REGISTRY 和脚本元数据
  common.py            # 两个以上脚本复用的通用工具
  payments.py          # 支付、充值、银行付款
  purchase.py          # 采购、拍下、上架
  warehouse.py         # 仓库、配送、箱子相关
  full_flow.py         # 全流程和恢复流程编排
  oem/
    common.py          # OEM 通用登录、请求、翻译、上传
    inquiry.py         # OEM 询价
    sample_order.py    # OEM 样品单
    balance_pay.py     # OEM 余额支付
```

如果某个业务域已经有对应文件，新脚本优先放入该业务域文件；只有脚本逻辑明显独立且体量较大时，才新建独立文件。

## 脚本入口规范

每个数据脚本必须提供统一入口：

```python
def run_xxx_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ...
```

返回值必须保持四元组：

```text
passed: bool          # 是否成功
log_text: str         # 可读日志，通常是 JSON 文本
report_path: str      # 报告路径
summary: dict         # 前端和接口使用的摘要
```

要求：

- `variables` 必须先复制成新字典，避免污染调用方传入对象。
- 脚本必须调用现有报告写入能力，保持报告路径可追踪。
- 失败时也必须返回四元组，不允许直接抛出未处理异常。
- `summary` 中已有字段含义不得随意改变。

## 新增脚本流程

1. 选择业务域文件，避免修改无关脚本。
2. 编写 `run_xxx_script` 入口和当前脚本私有辅助函数。
3. 如果需要公共函数，先确认至少两个脚本复用；否则留在当前脚本文件。
4. 在 `registry.py` 或当前兼容注册位置登记脚本 key、名称、函数和说明。
5. 在 `app/data_scripts/__init__.py` 导出入口，保证旧导入方式可用。
6. 如果需要 API 入口，再在 `app/routers/data_scripts.py` 增加对应路由。
7. 补最小测试，覆盖导入、参数校验、成功路径、失败路径和注册表。
8. 运行验证命令，确认旧脚本入口数量不减少。

## 禁止事项

- 不允许把整段新业务逻辑追加到 `app/data_scripts/__init__.py`。
- 不允许为了新增脚本而改动其他脚本的请求参数、返回格式、注册 key 或执行顺序。
- 不允许把只给一个脚本使用的函数抽到 `common.py`。
- 不允许复制粘贴大量已有脚本逻辑后只改少量字段；应抽取明确公共能力或保留在业务域内复用。
- 不允许绕过 `SCRIPT_REGISTRY` 直接在前端或路由里硬编码新脚本。
- 不允许新增真实账号、密钥、环境地址到代码或文档。

## 注册检查

新增或修改脚本后，必须检查：

```python
import app.data_scripts as ds

entries = [
    name for name, value in vars(ds).items()
    if name.startswith("run_") and name.endswith("_script") and callable(value)
]

assert len(entries) >= 22
assert "SCRIPT_REGISTRY" in vars(ds)
```

`SCRIPT_REGISTRY` 中每个启用脚本必须满足：

- `func` 指向可调用函数。
- `name` 是前端可读名称。
- 注册 key 稳定，不因重构随意改名。
- 删除或替换旧脚本必须先单独确认。

## 测试要求

新增脚本后至少运行：

```powershell
python -m compileall -q app tests
python -m pytest tests -q --tb=short
```

如果只修改单个脚本，也要先跑相关最小测试，再根据风险决定是否跑完整测试。

必须重点确认：

- 旧脚本入口数量不减少。
- `SCRIPT_REGISTRY` 可正常导入。
- 相关 API 不返回 404。
- 新脚本成功和失败路径都返回四元组。
- 不影响已有脚本测试。

## AI 协作要求

让 AI 新增或修改数据脚本时，建议明确提供：

```text
脚本名称：
所属业务域：
输入变量：
成功条件：
失败时怎么判断：
是否需要新增 API 入口：
是否复用已有脚本或公共函数：
不允许影响哪些已有脚本：
```

如果信息不完整，AI 必须先阅读现有相关脚本，再列出计划并等待确认；不得直接把新逻辑塞进大文件。
