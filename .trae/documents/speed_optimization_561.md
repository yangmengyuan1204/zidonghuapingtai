# 脚本执行速度优化方案（基于 #561）

## Summary

针对用户反馈的 #561 执行耗时 63093ms（未跑全流程）的问题，对 `shopping_cart` 与 `order_offered` 两个节点做最小改动的速度优化。预期将单次半流程耗时从 ~63s 降至 ~35-40s，功能完整性不变。

## Current State Analysis（基于 #561 实测数据）

| 节点 | 耗时 | 占比 | 主要耗时点 |
|------|------|------|-----------|
| shopping_cart | 44461ms | 70% | `collect_items` 对首页 50 条搜索结果逐条 `fetch_goods_detail`，`detail_workers` 默认仅 4 |
| order_offered | 18620ms | 30% | 后端流程串行 7 次 admin API，含 2 次冗余 detail 查询；`cart_list` 与 `option_list` 串行 |

证据来源：
- [test_record 561 log](file:///d:/A_zidonghuapingtai/auto_test_platform.db)
- [shopping_cart allure 日志](file:///d:/A_zidonghuapingtai/reports/allure-results/d38e9fb8-bdf6-4727-9433-0ec9aae1d992-log.txt)（首页 7 店 21 商品，但 detail 阶段处理整页 50 条）
- [order_offered allure 日志](file:///d:/A_zidonghuapingtai/reports/allure-results/0778bc06-4851-4d87-b228-1b35fdbfcdb7-log.txt)（backend.steps 显示 login→detail→translate→detail_after_translate→confirm→detail_after_confirm→offer→detail_after_offer）

## Proposed Changes

### 改动 1：提升 `detail_workers` 默认值 4 → 8

**文件**：[app/data_scripts.py](file:///d:/A_zidonghuapingtai/app/data_scripts.py#L892)

**What**：`detail_workers = _as_int(variables.get("detail_workers"), 4)` → 默认值改为 `8`

**Why**：`collect_items` 内 `fetch_goods_detail` 是 IO 密集型（每次 1 次 HTTP 搜索调用），detail_workers=4 时 50 条商品需 ~13 轮；提升到 8 后 ~7 轮，detail 阶段耗时接近减半。后端 API 已验证可承受 4 并发，8 并发在 Rakumart 限流阈值内。

**How**：单行默认值修改。full_flow 路径未显式 setdefault detail_workers（[L7994-8012](file:///d:/A_zidonghuapingtai/app/data_scripts.py#L7994)），会落到 run_shopping_cart_script 的默认值，因此改一处即可覆盖。

**风险**：低。`multiprocessing.pool.ThreadPool` 已封装异常，单条失败不影响整体。

---

### 改动 2：`collect_items` 内 detail 阶段增加早停

**文件**：[app/vendor/piliangtianjiagouwuche.py](file:///d:/A_zidonghuapingtai/app/vendor/piliangtianjiagouwuche.py#L1024-L1055)

**What**：在 `collect_items` 函数的 detail 拉取循环中，加入"按需早停"——detail 阶段采用分批处理（每批 10 条），每批结束后立即检查 `ready >= target_shops`，命中则跳过本页剩余商品的 detail 拉取。

**Why**：#561 实例中 target_shops=4 × per_shop=5 = 20 件即够，但当前代码对整页 50 条全部拉 detail，浪费 ~30 次 HTTP 请求（约 6-10s）。早停后可省去这部分。

**How**：
- 保留 ThreadPool.map 的批量处理方式，但把整页 goods 切成 chunk_size=10 的小批
- 每批 map 完成后立即 build_cart_candidates + 分组，检查 `ready >= target_shops`
- 命中则 `break` 跳出 detail 循环（外层页循环已有相同检查 L1050-1051）

**功能完整性**：不变。早停条件就是原有的 `ready >= target_shops`，只是从"整页后检查"提前到"每批后检查"。

**风险**：中。需保证分批后店铺桶累加逻辑与原逻辑一致。

---

### 改动 3：跳过 `detail_after_translate` 冗余查询

**文件**：[app/data_scripts.py](file:///d:/A_zidonghuapingtai/app/data_scripts.py#L2075-L2076)

**What**：在 `_run_backend_order_flow` 中删除/跳过 `_, after_translate = _order_detail_data(...)` 调用，`backend_log["detail_after_translate"]` 改为复用 `detail_before` 的 order_data；`confirm_source` 直接用 `translate_data`（已是本地构造的数据，包含 order_detail）。

**Why**：translate 接口仅做翻译，status 从 20→21 变化，但 `confirm_source` 实际只读 `order_detail` 数组（[L2088](file:///d:/A_zidonghuapingtai/app/data_scripts.py#L2088)），translate_data 已包含该数组。省 1 次带 retries=2 的 admin detail 请求（约 1.5-3s）。

**How**：
- 删除 L2075 的 `_order_detail_data` 调用
- `backend_log["detail_after_translate"]` 改为 `_admin_detail_brief(order_data)`（复用 detail_before 的数据，标注 `cached_from: "detail_before"`）
- L2088 `confirm_source = after_translate or translate_data` 改为 `confirm_source = translate_data`

**功能完整性**：不变。translate 不修改 order_detail 结构，confirm_data 构造只需 order_detail + variables。

**风险**：低。已确认 `_build_confirm_data` 入参只需 order_detail 列表，与 detail_after_translate 无字段差异。

---

### 改动 4：`order_offered` 暂停点跳过 `detail_after_offer`

**文件**：[app/data_scripts.py](file:///d:/A_zidonghuapingtai/app/data_scripts.py#L2137-L2148)

**What**：在 `_run_backend_order_flow` 的 offer 成功分支中，仅当 `order_offered` 不是暂停终点（即用户配置 `stop_after_node` 超过 `order_offered`）时才调用 `detail_after_offer`；暂停点直接复用 `after_confirm` 的 status 字段（标注 `status_source: "after_confirm"`）。

**Why**：#561 的 `stop_after_node=order_offered`，offer 提交后立即暂停，不需要读取最新 status（后端 status 异步更新，读出来也是 30 或 22，对暂停结果无影响）。省 1 次 retries=1 的 admin detail 请求（约 1-2s）。

**How**：
- 在 L2139 `_checkpoint_requested(variables, "order_offered")` 命中时，跳过 L2137 的 `_order_detail_data` 调用
- `backend_log["detail_after_offer"]` 在暂停分支设为 `{"skipped": True, "reason": "paused_at_order_offered"}`
- `backend_status` 在暂停分支用 `after_confirm.get("status")`（保守值）

**功能完整性**：不变。非暂停路径（继续到 order_paid）仍调用 detail_after_offer 获取真实 status。

**风险**：低。仅在暂停分支跳过，非暂停路径行为完全不变。

---

### 改动 5：`cart_list` 与 `option_list` 并行

**文件**：[app/data_scripts.py](file:///d:/A_zidonghuapingtai/app/data_scripts.py#L6246-L6340)

**What**：在 `run_order_quote_script` 中，当 `option_counts` 非空时，把 `cart_list` 请求与 `_fetch_order_option_catalog` 请求并行化（用 `concurrent.futures.ThreadPoolExecutor`，max_workers=2）。

**Why**：当前 cart_list（~1-2s）与 option_list（~1-2s）串行，并行后节省 ~1-2s。两者无数据依赖（option_catalog 应用于 selected_items 之后）。

**How**：
- 在 L6246 之前判断 `option_counts`，若非空则用 ThreadPoolExecutor 同时提交 cart_list 和 option_catalog 两个 future
- cart_list 结果继续走 L6250 的 `_flatten_cart_goods` 流程
- option_catalog 结果在 L6334 复用（避免重复请求）
- 若 `option_counts` 为空，保持原串行逻辑

**功能完整性**：不变。两个请求原本就独立，仅执行顺序从串行变并行。

**风险**：低。需注意 `_fetch_order_option_catalog` 内部异常处理；用 future.result() 捕获异常后回退到串行重试。

---

## Assumptions & Decisions

1. **范围确认**：仅优化 #561 涉及的 shopping_cart + order_offered 两节点，不触碰 shelf_stored / porder_offered / admin token 跨节点缓存（用户已确认）
2. **冗余查询确认**：允许跳过 detail_after_translate 与 order_offered 暂停点的 detail_after_offer（用户已确认）
3. **detail_workers 上限**：8 并发在 Rakumart API 限流阈值内（基于现有 4 并发稳定运行的观察，翻倍风险可控）
4. **不改 API 路径、字段构造、重试策略**：仅优化调用顺序与并发度
5. **不改 allure 日志结构**：跳过的查询在日志中标注 `skipped/cached_from`，保持可追溯性
6. **不打包用户工作区其他未提交改动**：commit 时仅含本次 5 项改动的相关文件

## 预期效果

| 节点 | 优化前 | 优化后（预估） | 节省 |
|------|--------|---------------|------|
| shopping_cart | 44461ms | ~25000-30000ms | 14000-19000ms |
| order_offered | 18620ms | ~12000-14000ms | 4000-6000ms |
| **合计** | **63093ms** | **~37000-44000ms** | **~19000-26000ms** |

## Verification Steps

1. **语法检查**：`py -c "import ast; ast.parse(open('app/data_scripts.py', encoding='utf-8').read()); ast.parse(open('app/vendor/piliangtianjiagouwuche.py', encoding='utf-8').read()); print('OK')"`

2. **单元测试（如已有）**：
   ```
   py -m pytest tests/test_reliability_improvements.py -x
   ```
   注意：用户工作区有未提交的 test_balance_recharge.py / test_locator_heal.py，本次不触碰

3. **端到端验证**：以 #561 相同配置（target_shops=4, per_shop=5, stop_after_node=order_offered）重跑全流程脚本，对比：
   - `duration_ms` 总耗时下降
   - `shopping_cart.duration_ms` 下降
   - `order_offered.duration_ms` 下降
   - `order_offered.backend.detail_after_translate` 含 `cached_from` 标注
   - `order_offered.backend.detail_after_offer` 含 `skipped` 标注（暂停点）
   - 业务结果 `passed=true`，`order_sn` 正常生成，`backend_status=30`

4. **回归检查**：
   - 非暂停路径（stop_after_node=porder_offered）下，detail_after_offer 仍正常调用
   - option_counts 为空时，cart_list 仍串行执行（无并行副作用）
   - detail_workers=8 下后端不返回限流错误（429/503）

5. **Git 提交**：仅 `git add app/data_scripts.py app/vendor/piliangtianjiagouwuche.py`，不打包用户其他未提交改动
