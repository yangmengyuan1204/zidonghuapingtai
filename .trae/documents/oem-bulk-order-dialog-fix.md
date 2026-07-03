# OEM 大货单弹窗问题修复计划

## 摘要
修复大货单执行弹窗的两个问题：①状态展示为数字需映射为中文标签；②工厂链接超长不换行。

## 当前状态分析

- [static/app.js](file:///d:/A_zidonghuapingtai/static/app.js) L2103-2130 `renderSkuTable` 函数中：
  - L2118 `infoFields` 映射了 `status: "状态"`，但直接展示原始数字值（如 0/1/2/3...），无中文标签
  - L2124 工厂链接展示在 `<span>` 内，CSS 为 `display:flex;flex-wrap:wrap;gap:4px 16px`，但 URL 本身不换行
- 询价单 `status` 字段的含义需要通过实际 API 响应确认
- OEM 询价单流程中 `detail_list[].status` 值：0=默认、1=询价完成、2=报价完成（来自 [app/data_scripts.py](file:///d:/A_zidonghuapingtai/app/data_scripts.py) L9330/L9386）

## 改动文件清单

### 1. [static/app.js](file:///d:/A_zidonghuapingtai/static/app.js) — 修复两个问题

**问题1：状态数字映射为中文标签**

在 `renderSkuTable` 函数内（L2103），新增状态映射函数：

```javascript
const OEM_INQUIRY_STATUS_MAP = {
  0: "待翻译", 1: "待审核", 2: "待询价", 3: "询价中",
  4: "待报价", 5: "报价中", 6: "已完成", 7: "已取消",
};
function oemInquiryStatusLabel(v) {
  const n = Number(v);
  if (!isNaN(n) && OEM_INQUIRY_STATUS_MAP[n]) return `${OEM_INQUIRY_STATUS_MAP[n]}(${n})`;
  return v != null ? String(v) : "-";
}
```

在 L2122 `infoFields` 循环中，`status` 字段使用 `oemInquiryStatusLabel(v)` 替代直接展示。

**问题2：工厂链接换行**

在 L2124 `infoHtml` 的容器样式中，添加 `word-break:break-all;overflow-wrap:anywhere`。

具体改动点：
- L2117-2124 区域，`renderSkuTable` 内的 `infoFields` 渲染逻辑

## 假设与决策

- 状态映射基于 OEM 询价单流程推断（0-7），实际值需通过 API 响应验证
- 如果实际 status 值不在映射表中，回退展示原始值
- 工厂链接换行使用 `word-break:break-all` 确保长 URL 能在任意位置断行
- 问题3（SKU 大货字段缺失）和大货单参数样式重构暂不处理，等用户提供接口后再做

## 验证步骤
1. 前端打开大货单弹窗，输入已完成的询价单号查询
2. 确认状态字段显示为"中文标签(数字)"格式
3. 确认工厂链接超长时自动换行，不撑破布局
4. 如果状态映射不对，根据实际 API 返回的 status 值调整映射表
