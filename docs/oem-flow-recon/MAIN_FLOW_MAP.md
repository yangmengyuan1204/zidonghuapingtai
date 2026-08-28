# OEM 主流程抓包映射（五条）

抓取时间：2026-08-15。仓库：`D:\A_zidonghuapingtai`。凭证不入库。

口径：**阶段列表/详情读接口 = 浏览器实抓**；**推进写接口 = 详情页 JS 真实调用形态**（未对线上单据点确认，避免误推进）。询价部分写 body 与 `app/core/data_script_catalog.py` 历史登记一致时可直接复用。

原始产物：`61_*.json/png`、`64_detail_write_payloads.json`、`65_*`、`66_*`、`68_*`、`69_*`。

---

## 环境

| 角色 | Origin | API |
|------|--------|-----|
| 前台 | `https://oem.rakumart.cn` | `https://oemapi.rakumart.cn` + Bearer（`OEM-PC-UUID`） |
| 后台 | `https://oemadmin.rakumart.cn` | 同上 + `/admin/login`（`OEM_PC_BG_TOKEN`） |

---

## 1. 询价

### 阶段（停止节点）与列表读接口

| 停止节点 | 后台路由 | 列表 API | 实抓 body 要点 |
|----------|----------|----------|----------------|
| 进行中 | `#/inquiryOrderList` | `POST /admin/inquiryList` | `status:"100"`, page/pageSize, y/g/f_id |
| 翻译阶段 | `#/inquiryTranslationStage` | `/admin/translateInquiryList` | 同上 |
| 翻译审核 | `#/inquiryTranslationAuditStage` | `/admin/translateAuditList` | 同上 |
| 询价阶段 | `#/inquiryInquiryStage` | `/admin/gInquirtList` + `/admin/inquiryNum` `{point:2}` | |
| 报价阶段 | `#/inquiryQuotationStage` | `/admin/qouteInquirytList` + `inquiryNum` `{point:3}` | |
| 作业完成 | `#/inquiryHomeworkCompleted` | `/admin/complateInquiryList` + `inquiryNum` `{point:4}` | |

前台列表：`POST /api/inquiryList`，**`status` 必须是 `100`**（不是 10000）。

详情读：

- 后台：`POST /admin/inquiryDetail` `{order_sn, is_quote}`；带 `stage` query 时附加 `point_name`
- 前台：`/api/inquiryDetail`（报价工厂列表在 `data.list`）

### 推进写接口（JS 形态）

| 动作 | API | Body 形态 |
|------|-----|-----------|
| 保存/提交翻译 | `/admin/inquiryTranslate` | `{is_temp, order_sn, goods_name_tr, material_tr, customize_detail_tr, goods_detail_tr, goods_file_tr, sku_info, goods_id, goods_class, y_remark, user_remark}` |
| 提交审核/采购 | `/admin/inquiryTranslateAudit` | `{order_sn}` |
| 开始询价 / 询价完成 / 报价完成等 | `/admin/inquiryStartInquiry` 等 | **`{...inquiryDetail整包, order_sn}`**（动态 `$api[t]({...d.value, order_sn})`） |
| 工厂报价 / 报价给客户 | `/admin/factoryQuote`、`/admin/factoryQuoteToUser` | **`{...工厂detail行, order_sn, is_temporarily, detail_id}`** |
| 编辑/添加工厂 | `/admin/factoryEdit`、`/admin/factoryAdd` | `detail_id`/`order_sn` + 工厂字段 |
| 开始报价阶段 | `/admin/inquiryStartQuote` | `{order_sn}` |

`point_name`：详情提交节点语义（catalog：`translation` / `inquiry`），与不带 `point_name` 的详情查询是同一 URL 不同语义。

前台创建：`POST /api/newInquiry`（前端方法名 `createnewGoods` → 同一 URL；catalog `oem_new_inquiry` 已有完整字段模板）。辅料创建页会调 `/api/getAccessoryType`、`/api/getGoodsList`。

---

## 2. 样品

| 停止节点 | 列表 API | 实抓 body |
|----------|----------|-----------|
| 进行中 | `/admin/samplesList` | `status:"10000"`, y_id/f_id, page… |
| 翻译 | `/admin/samplesTranslatedList` | 同上 |
| 确认 | `/admin/samplesConfirmedList` | + `samplesNum` `{point:2}` |
| 报价 | `/admin/samplesQuote` | `{point:3}` |
| 生产 | `/admin/samplesInproduction` | `{point:4}` |
| 派送与作业 | `/admin/samplesWorking` | `{point:5}` |

前台：`/api/orderList` `order_type=1`, `status=10000`；详情 `/api/orderDetail`（含 `price_info` / `progress_list`）。

后台详情：`POST /admin/samplesDetail` `{order_sn}`。

### 推进写（JS）

| 动作 | API | Body |
|------|-----|------|
| 开始确认 | `samplesStartConfirm` | `{order_sn}` |
| 确认完成 | `samplesConfirmed` | `{warehouse_city, is_special_quote, order_sn, y_response, quote_info}` |
| 开始报价 | `samplesStartQuote` | `{order_sn}` |
| 报价给用户 | `samplesQuoteToUser` | `{order_sn, warehouse_city}` |
| 前台入金 | `/api/balancePayOrder` | `{order_sn}`（报价给用户后解锁采购） |
| 开始采购 | `samplesStartPurchase` | `{order_sn}` |
| 采购完成 | `samplesPurchaseCompleted` | `{order_sn}` |
| 派送 | `samplesDispatch` | `{express_id, order_sn, express_no, express_remark}` |
| 退回翻译 | `samplesBackTranslation` | `{order_sn}` |
| 重报价 | `samplesReQuote` | `{order_sn}` |

详情页可见按钮示例（确认阶段）：`开始确认`、`退回翻译`。

---

## 3. 大货

列表：`largeList` / `largeTranslatedList` / `largeConfirmedList` / `largeQuoteList` / `largeInproductionList` / `largeWorkingList`，body 同样品并多 `p_id`，`status:"10000"`。

详情：`/admin/largeDetail` `{order_sn}`；前台 `order_type=2`。

### 推进写（JS）

与样品同构：确认/报价/入金/采购完成同样品；大货派送前常需 `productionSyncYadmin|User` +（可选）`skipFinalPurchasePayment` → 待出货后 `largeDispatch{order_sn}`；快递 `largeExpressAdd/Edit/Del(express_id)`。

---

## 4. 配送单

| 停止节点 | 列表 API | status |
|----------|----------|--------|
| 进行中 | `/admin/allPorder` | `"1000"` |
| 翻译 | `/admin/porderTransalte` | `"1000"` |
| 装箱 | `/admin/porderPacking` | `"1000"` |
| 报价 | `/admin/porderQuote` | `"1000"` + `porderNum` `{father_status:30}` |
| 出货 | `/admin/porderShipment` | `"1000"` |
| 国际派送 | `/admin/porderDispatched` | `"1000"` |

前台：`/api/porderList` **`status:1000`**，字段 `porder_sn`/`express_no`。

详情：`/admin/porderDetail` `{porder_sn}`（含 `price_info`）。

### 推进写（JS）

| 动作 | API | Body |
|------|-----|------|
| 开始翻译 | `porderStartTransalte` | `{porder_sn}` |
| 提交翻译→装箱 | `porderSubmitTranslate` | `{porder_sn, y_remark, detail_list[{detail_id,y_remark,warehouse_list}], warehouse_type}` |
| 添加箱子 | `addBox` | `{porder_sn, type, box_num, length, width, height, weight}` |
| 装箱入箱 | `boxPacking` | `{box_id, packing_info:[{porder_detail_id, pack_num, warehouse_city}]}` |
| 装箱完成 | `porderPackingComp` | `{porder_sn, box_info}`（字段名是 box_info） |
| 国际单号 | `savePorderExpress` | `{box_id, express_no}` |
| 提出报价 | `porderRaiseQuote` | `{porder_sn, other_price, box_info(含logistics_id), detail_list}` |
| 前台支付 | `/api/balancePayPorder` | `{porder_sn}` |
| 出货 | `porderShipGoods` | `{porder_sn}` |
| 签收 | `porderSign` | `{porder_sn}` |
| 回退 | `porderBackTransalte` / `porderBackPacking` | `{porder_sn}` |

详情页可见：`开始翻译`（待业务翻译）。

---

## 5. 辅料

- 前台商品：`/user/accessory` → `/api/accessoryList`
- 后台列表：`/#/listOfAuxiliaryMaterials` → `/admin/manage.accessoryList`
- 辅料询价单号后缀常见 `-FL`；推进 API 族：`submitTranslate` / `accessoryStartInquiry` / `accessoryQuoteToUser` 等（与询价平行，第一版可挂在询价链 `goods_type`）

---

## 金额比对

读字段（实抓存在）：

- 样品/大货前台 `orderDetail.price_info`（`samples_*` / `large_*` / `real_payment*`）
- 配送 `porderDetail.price_info`（`total_fee*` / `logistics_fee*` / `real_payment_jpy`）

**不要**套日本站计算器。

---

## 跟进 / 工厂报价（非独立业务）

- 跟进列表：`/admin/goodsManage/followUpList`
- 工厂报价：询价详情内对 `detail_list` 行调用 `factoryQuote`，属询价阶段内功能

---

## 本轮未做 / 缺口

1. ~~未对线上单据点击写按钮~~ → **已用 user15 单据实测**，见 [LIVE_WRITES_USER15.md](LIVE_WRITES_USER15.md)。
2. ~~采购/装箱完成~~ → 已实测：入金→StartPurchase→PurchaseCompleted；addBox→boxPacking→porderPackingComp（见 LIVE）。
3. 前台 `newInquiry` 精简 body 仍报 `エラー`，创建页完整字段待再抠。
4. 已推进单号（勿重复乱点）：样品/大货已采购完成(36)；配送已装箱完成(5)；询价已报价完成。

---

## 造数编排建议（给产品）

停止节点 = 上表「阶段」列。选「停在确认阶段」→ 自动跑完前面阶段写接口，停在该节点。金额开关挂在业务类上，在报价/支付相关节点比对 `price_info`。
