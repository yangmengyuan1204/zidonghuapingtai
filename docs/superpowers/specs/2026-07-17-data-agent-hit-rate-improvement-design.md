# DeepSeek 数据智能体命中率提升设计

## 问题现状

自然语言→结构化 goal 的命中率 < 50%，目标理解、工具选择、参数提取均需提升。用户使用 DeepSeek-4-pro 模型，排除模型能力不足因素。

## 根因分析

| 瓶颈 | 严重程度 | 详情 |
|---|---|---|
| system prompt 仅 14 字 | 🔴 高 | `"你是资深软件测试工程师，只输出合法 JSON。"` — 无领域知识注入 |
| 零 few-shot 示例 | 🔴 高 | `_analysis_prompt` 496 行规则，零条正确输出示例，模型无参照物 |
| 确定性正则覆盖窄 | 🟡 中 | `reduce_intent_fields` 仅覆盖 ~10 种模式（6 个目标节点 + 数量/价格），大量口语表达漏过 |
| 单次调用无纠错 | 🟡 中 | 一次 `call_local_model_json` 出结果，错了无法自我修正 |
| prompt 臃肿 | 🟡 中 | `_analysis_prompt` 496 行规则堆砌 + `_agent_action_prompt` 497 行策略混排，模型容易漏关键约束 |

## 方案

方案 1（Prompt 工程优化）+ 方案 2（确定性匹配增强）组合，分两个阶段实施。

### 阶段一：Prompt 工程优化（低风险，快速见效）

#### 1.1 新增 prompt 模块

新建 `app/services/data_factory_agent_prompts.py`，集中管理所有 prompt：
- `SYSTEM_PROMPT` — 领域知识 + 行为约束
- `ANALYSIS_FEW_SHOT_EXAMPLES` — 5 个典型场景的消息→正确输出示例
- `build_analysis_prompt(messages, intent_state)` — 组装分析 prompt
- `build_action_prompt(goal, events, state)` — 组装执行 prompt

#### 1.2 system prompt 重构

从 14 字扩展为：
- 业务领域描述（日本站全流程、核心变量）
- 5 条行为铁律（只输出 JSON、不可信输入、目标不明必追问、价格口径不明必追问、默认值记录 assumptions）

#### 1.3 few-shot 示例注入

在 `_analysis_prompt` 末尾追加 5 个示例，覆盖：
1. 简单下单："帮我开一个1688店铺，买2件衣服，做到待付款"
2. 多店铺+银行支付："开3个店每店1个商品，银行汇款支付，上架入库"
3. 续跑+问题产品："订单SN2024xxx，把问题产品处理掉"
4. 配送单场景："配送单P2024xxx做到配送单支付"
5. 多操作："先下单到待付款，然后处理问题产品"

示例格式：用户消息 + 正确 JSON 输出，嵌入 prompt 末尾。

#### 1.4 prompt 规则精简

`_analysis_prompt` 14 条规则精简为核心 8 条：
1. 目标节点映射表（铁律，不可被覆盖）
2. 店铺/商品数量计算规则
3. 价格口径判定（合并 3 条→1 条）
4. 支付方式映射
5. 默认值策略（合并 5 条→1 条）
6. 多操作编排规则
7. 安全约束
8. 最新消息优先 + 已确认保留

`_agent_action_prompt` 497 行重整为：
- 前置状态摘要（1 行）
- 工具选择优先级表（场景→首选→备选）
- 核心恢复策略（3 条）

#### 1.5 model_client system prompt 参数化

`call_local_model_json` 新增可选参数 `system_prompt: str = ""`，允许调用方传入自定义 system prompt，替代默认的 14 字模板。`_analysis_prompt` 和 `_agent_action_prompt` 调用时传入领域 system prompt。

### 阶段二：确定性匹配增强（中等风险）

#### 2.1 扩展 reduce_intent_fields

新增匹配模式（10→50+）：

| 类别 | 现有 | 新增 |
|---|---|---|
| 目标节点 | 6 模式 | +15（到报价就停、只要翻译、确认后就行、付完钱、核查完、配送就行...） |
| 店铺/商品 | 3 模式 | +8（"N家店"、"每个店铺各M个"、"总共N件"、"分别来自N家店"...） |
| 关键词 | 0 | +3（"搜XX"、"关键词YY"、"用ZZ"） |
| 支付方式 | 0 | +5（"银行汇款"、"余额支付"、"合并付款"、"便利店"、"信用卡"） |
| 操作序列 | 0 | +3（"先A再B"、"A然后B"、"A并且B"） |
| 选项/附加服务 | 0 | +3（"不加option"、"随机N个附加服务"、"指定XXX服务"） |

#### 2.2 确定性→LLM 两级路由

```
用户消息
  → reduce_intent_fields() 确定性提取（扩展版）
  → resolved_fields 覆盖 mode/target_node/customer_ids/核心变量
  → 如果 resolved_fields 已覆盖所有关键字段 → 直接构造 goal，跳过 LLM
  → 否则 → LLM 分析（带上已提取字段作为已确认字段）
```

关键：确定性匹配的结果作为 `intent_state.resolved_fields` 传入 prompt，LLM 看到已确认字段后只需补充剩余部分，减少 LLM 自由发挥空间。

### 阶段三（后续迭代，本次不实施）

- 多轮反思：LLM 输出后自动校验关键字段（target_node 是否在合法枚举中、数量是否为正整数），不通过则自动追加一轮修正调用
- 案例库 RAG：存储历史成功 goal，相似消息检索后作为动态 few-shot

## 改动文件

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `app/services/data_factory_agent_prompts.py` | 新增 | 集中管理所有 prompt |
| `app/services/data_factory_agent_intent.py` | 修改 | 扩展正则匹配模式 |
| `app/services/data_factory_agent.py` | 修改 | `_analysis_prompt`→调用新模块；`_agent_action_prompt`→调用新模块；`_analyze_turn` 兼容确定性路由 |
| `app/functional_testing/model_client.py` | 修改 | `call_local_model_json` 新增 `system_prompt` 参数 |
| `tests/test_data_factory_agent.py` | 修改 | 新增命中率回归测试 |

## 不变项

- 不修改数据库/API 接口/JWT 认证
- 不修改执行流程（`_run_agent_session` / `_next_agent_action` 循环逻辑不变）
- 不修改工具注册/执行（`TOOL_SPECS` / `execute_agent_tool` 不变）
- 不修改数据脚本（`app/data_scripts/` 零改动）
- `goal` JSON Schema 不变，向下兼容

## 验收标准

1. 现有测试全部通过
2. 新增 10 个命中率回归 case（覆盖：简单下单、多店铺、银行支付、续跑、问题产品、配送单、多操作、口语表达、边界值、歧义澄清），全部命中正确 goal
3. 不影响已有功能（购物车、报价、支付、配送单流程均可正常触发）
