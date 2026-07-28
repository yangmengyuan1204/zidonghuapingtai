# Optional Domestic Freight Design

## Goal

订单造数只有在用户自然语言或确认合同明确填写国内运费时，才向采购调查与业务报价请求写入运费；未要求时不生成、不展示默认 5、不提交对应字段。

## Rules

- 未提供 `confirm_freight`、`offer_freight` 或兼容字段 `freight`：合同不注入默认值，请求不携带运费字段。
- 明确填写 `0`：保留并提交字符串 `"0"`。
- 明确填写正数：标准化后提交对应金额。
- 未填写运费时，`offer_total` 计算内部按 0 处理，但不得因此向请求补写运费字段。
- 不改变商品价格、其他费用、采购运费及问题产品退款运费规则。

## Scope

- 智能体新订单默认合同：`app/services/data_factory_agent.py`
- 订单采购调查与业务报价载荷：`app/data_scripts/order_support.py`
- 回归测试：`tests/test_data_factory_agent.py`

## Verification

- 先以记录 `#1165` 同类输入证明当前代码会产生默认 5。
- 覆盖未填写、显式 0、显式正数。
- 运行智能体、订单脚本和权限相关聚焦回归。
