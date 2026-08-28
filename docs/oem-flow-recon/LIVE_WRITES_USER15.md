# User15 写按钮实测记录（2026-08-15）

账号：前台 user_id=15（小杨测试账号）。后台操作账号 admin。  
原始 JSON：`81_*`、`82_*`、`84_*`、`85_quote_writes.json`、`86_inquiry_factory_quote.json`。

## 实抓成功（真实 POST + 状态变化）

### 询价 `X20260805143420-15-OEM`

| 步骤 | API | Body 要点 | 结果 |
|------|-----|-----------|------|
| 翻译保存 | `/admin/inquiryTranslate` | 必须 `goods_class`（如 110）+ `*_tr` + `sku_info` | code=0 |
| 提交审核 | `/admin/inquiryTranslateAudit` | `{order_sn}` | y=2,g=1,u=2 |
| 开始询价 | `/admin/inquiryStartInquiry` | **详情整包** | g→2 |
| 编辑工厂 | `/admin/factoryEdit` | `detail_id` + 工厂字段（name 不能空） | code=0 |
| 工厂报价 | `/admin/factoryQuote` | detail 行 + `large_deposit_rate`∈(0,100] + sku 价格>0 | code=0 |
| 报价给客户 | `/admin/factoryQuoteToUser` | `{...detail行, order_sn, detail_id}` | code=0 |
| 询价完成 | `/admin/inquiryComplete` | 详情整包 | code=0 |
| 开始报价 | `/admin/inquiryStartQuote` | `{order_sn}` | code=0 |
| 报价完成 | `/admin/inquiryQuoteComplate` | 详情整包 | y=5,g=4,u=4；工厂 status=2 报价完成 |

校验教训：定金比例不可 ≤0 或 >100；SKU/运费价格不可 ≤0；工厂名为空会报「工厂为空」。

### 样品 `Y20260403172102-15-OEM`

| 步骤 | API | Body | 状态 |
|------|-----|------|------|
| 开始确认 | `samplesStartConfirm` | `{order_sn}` | 10→12 |
| 确认完成 | `samplesConfirmed` | `order_sn,warehouse_city,is_special_quote,y_response,quote_info{...sku_info}` | 12→20,point=3 |
| 开始报价 | `samplesStartQuote` | `{order_sn}` | code=0 |
| 报价给用户 | `samplesQuoteToUser` | `{order_sn,warehouse_city}` | 20→**24** |
| 前台入金 | `/api/balancePayOrder` | `{order_sn}`（先 `paymentDetail`） | 余额支付成功；admin_status→**30** |
| 开始采购 | `samplesStartPurchase` | `{order_sn}` | 30→**32** |
| 采购完成 | `samplesPurchaseCompleted` | `{order_sn}` | 32→**36** |
| 发货完成(派送) | `samplesDispatch` | `{express_id,order_sn,express_no,express_remark}`（生产中可点） | 36→**50** 国内派送中 |
| 填写快递单号 | `samplesExpressNo` | `{express_id,express_no,express_remark}` | code=0 |
| 配货签收 | `orderSign` | `{order_sn}` | 50→**52** 已签收 |
| 开始核查 | `checkStart` | `{order_sn}`（路径亦可 `/admin/checkStart `） | code=0 |
| 核查完成 | `checkComplete` | `{order_sn, check_list:[...sku行需 weight/check_num/长宽高]}`（字段名是 **check_list**） | →**54** 验货确认 |
| 提交客户 | `samplesCheckRaise` | `{order_sn}` | 54→**60** 等待上架 |
| 上架 | `orderShelve` | `{order_sn, shelve_info:[...], warehouse_city}` | 60→**64** 作业完成 |
| 提醒上架邮件 | `tipShelves` / `stockTipShelves` | `{order_sn}` | code=0 |

说明：未入金时 UI 只有「回退至报价」，`*SubmitPurchase`/`*PurchaseCompleted` 会报「当前状态无法操作」。`samplesCompPurchase` **路由不存在**（404 形态）。

### 大货 `D20260613110838-15-OEM`

| 步骤 | API | Body | 状态 |
|------|-----|------|------|
| 确认完成 | `largeConfirmed` | `order_sn,y_response,quote_info(含定金/option),warehouse_city,is_special_quote` | 12→20,point=3 |
| 开始报价 | `largeStartQuote` | `{order_sn}` | code=0 |
| 报价给用户 | `largeQuoteToUser` | `{order_sn,warehouse_city,sku_list}` | 20→**24** |
| 前台入金 | `/api/balancePayOrder` | `{order_sn}` | →**30** |
| 开始采购 | `largeStartPurchase` | `{order_sn}` | →**32** |
| 采购完成 | `largePurchaseCompleted` | `{order_sn}` | →**36** |
| 生产跟进同步 | `productionSyncYadmin` / `productionSyncUser` | `{order_sn,new_status}`（1..4 阶段） | 推进跟进标记 |
| 跳过尾款 | `skipFinalPurchasePayment` | `{order_sn}` | →**48** 待出货 |
| 发货完成 | `largeDispatch` | `{order_sn, express_nos:[...]}` | **已通** 48→50；多单复现（缺数组才 array_diff） |

### 配送 `OP20260302150837-15`

| 步骤 | API | Body | 状态 |
|------|-----|------|------|
| 开始翻译 | `porderStartTransalte` | `{porder_sn}` | 1→2 |
| 提交翻译 | `porderSubmitTranslate` | `{porder_sn,y_remark,detail_list[{detail_id,y_remark,warehouse_list}],warehouse_type}` | 2→**3**（装箱） |
| 添加箱子 | `/admin/addBox` | `{porder_sn,type,box_num,length,width,height,weight}`（`type` 必填） | box_list+1 |
| 装箱入箱 | `/admin/boxPacking` | `{box_id,packing_info:[{porder_detail_id,pack_num,warehouse_city}]}` | unpacked→0 |
| 装箱完成 | `porderPackingComp` | `{porder_sn,box_info}`（**不是** `box_list`；每箱需 `box_id`+尺寸重量+`detail[].box_num`） | 3→**5** |
| 写国际单号 | `savePorderExpress` | `{box_id, express_no}` | code=0 |
| 改物流/单号 | `updateExpressInfo` | `{porder_sn, express_info:[{box_id,express_no,new_express_no,new_logistics_id}]}` | 绑定 logistics_id |
| 提出报价 | `porderRaiseQuote` | `{porder_sn, other_price, box_info(含 logistics_id), detail_list:[{detail_id,warehouse_list}]}` | 5→**6**（物流需可算费，如 id=35） |
| 前台支付 | `/api/balancePayPorder` | `{porder_sn}` | code=0 |
| 出货 | `porderShipGoods` | `{porder_sn}` | →**9** |
| 签收 | `porderSign` | `{porder_sn}` | →**10** |
| 作业完成 | `porderComplete` | `{porder_sn}` | code=0 |

原始：`88_*`、`90_finish_final.json`。

## 编排规则（给造数引擎）

1. **只带单号**：`*StartConfirm` / `*StartQuote` / `*StartPurchase` / `*PurchaseCompleted` / `inquiryStartQuote` / `inquiryTranslateAudit` / `porderStartTransalte`
2. **读详情再回传整包**：`inquiryStartInquiry` / `inquiryComplete` / `inquiryQuoteComplate`
3. **读详情再改字段回传**：`factoryQuote` / `factoryQuoteToUser`；`samplesConfirmed` / `largeConfirmed`（带 `quote_info`）；`porderPackingComp`（`box_info` 来自详情 `box_list`）
4. **询价翻译前必须设 `goods_class`**
5. **工厂报价前必须 `factoryEdit` 填齐工厂名**
6. **样品/大货报价给用户后必须前台 `balancePayOrder`，才能 `*StartPurchase` → `*PurchaseCompleted`**
7. **样品派送**：生产中 `samplesDispatch{express_id,order_sn,express_no,express_remark}` → 国内派送中；可再 `samplesExpressNo` 补单号
8. **大货派送**：生产跟进 `productionSyncYadmin/User{order_sn,new_status}` →（可）`skipFinalPurchasePayment` → 待出货(48) → `largeDispatch{order_sn}`；快递 `largeExpressAdd/Edit`，删除字段名是 `express_id`
9. **配送装箱链**：`addBox`（含 `type`）→ `boxPacking`（`pack_num`）→ `porderPackingComp`（`box_info`）
10. **签收/核查/上架**：`orderSign` → `checkStart` → `checkComplete{check_list}` → `samplesCheckRaise` → `orderShelve{shelve_info,warehouse_city}`（样品已实测到 64）
11. **配送后半段**：箱子 `logistics_id`+`savePorderExpress` → `porderRaiseQuote` → `balancePayPorder` → `porderShipGoods` → `porderSign`
12. 金额比对：前台 `orderDetail`/`porderDetail` 的 `price_info`（不套日本计算器）

## 已推进单号（勿当干净单）

- 询价 `X20260805143420-15-OEM`（已报价完成）
- 样品 `Y20260403172102-15-OEM`（**作业完成 admin_status=64**）
- 大货 `D20260613110838-15-OEM` / `D20250709134928-15-OEM`（**64 作业完成**；发货需 `express_nos`；上架传 checkDetail 整行 sku + `shelve_num`）
- 配送 `OP20260302150837-15`（出货/签收后 **admin_status=10**）

## 仍缺口

- 前台 `newInquiry` 精简 body 仍 `エラー`（创建字段需从前台创建页再抠）
- 大货后半段参数已对齐 ApiPost：`largeDispatch.express_nos`；`orderShelve.shelve_info` 用核查 sku 整行并设 `shelve_num`（主单+对照单均到 64）

## 参数核对（2026-08-15）
- `largeDispatch`：`express_nos` 数组。对照单 `D20250709134928` / `D20260112100159` / `D20260727151004` / `D20260813154254` 均 48→50；`D20260126150236` 因问题产品拦截（业务错，非缺参）。
- 后半段同构：`orderSign`→`checkStart`→`largeCheckReport(check_report)`→`checkComplete(check_list)`→`largeCheckRaise`→`orderShelve`。
- `orderShelve`：`shelve_info` 需带 `checkDetail.sku_info` 整行并填 `shelve_num`（不是只有 `shelves_num` 的精简对象）。主单与对照单均到 **64**。
