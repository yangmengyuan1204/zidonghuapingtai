# Frontend V3 Light Workbench Visual Contract

## Authority

本合同只约束 Frontend V3 Workbench Redesign 的视觉实现。

- 源码决定功能，UI 图决定视觉。
- `docs/ui-redesign/README-CODEX.md` 与同目录 11 张最终 UI 图是本轮活动视觉依据。
- UI 图中的说明板、示例数据、示例状态和示例流程不是业务需求，不得据此新增功能。
- 源码中已有但图中未展示的菜单、按钮、字段、列、弹窗、状态和流程必须完整保留。

## Relationship to the Historical Contract

`docs/frontend-v2/visual-baseline/VISUAL-CONTRACT.md` 与
`docs/frontend-v2/visual-baseline/workbench-v1-v2-hybrid.png` 继续作为历史视觉基线原样保留。

在本次 Frontend V3 Light Workbench Redesign 中：

- 新 UI 图在颜色、尺寸、间距、排版、圆角、边框和组件外观上优先于旧的深色 232px / 62px 合同。
- 旧合同不得覆盖当前浅色设计。
- 旧代码中的业务行为、接口、权限、字段、状态和流程仍然全部保留。

## Active Implementation Tokens

以下颜色是根据最终 UI 参考图确定的实现 Token，不宣称是 README 明文规定的固定色值：

| Role | Value |
|---|---|
| Workspace | `#E8EEF5` |
| Sidebar | `#C9D9E7` |
| Primary action | `#245FA8` |
| Section surface | `#DDE7F0` |
| Panel | `#FFFFFF` |
| Border | `#B9C8D6` |
| Primary text | `#172B3F` |
| Sidebar width | `220px` |
| Topbar height | `56px` |
| Panel radius | `8px` |

## Component Rules

- 页面工作区使用冷灰蓝背景，内容使用白色 Panel。
- 左侧导航使用浅灰蓝背景；active 使用浅蓝底与钴蓝指示条。
- 顶栏保持 56px 左右，仅展示源码已有内容。
- Button、Input、Select、Table、Pagination、Modal、Badge 使用细边框、紧凑高度和清晰 focus。
- loading、empty、error、permission、disabled 只美化源码真实状态，不新增入口或 retry。
- 日志、JSON、宽表格通过换行、滚动和合理列宽保留全部内容。
- 禁止渐变、玻璃拟态、霓虹、重阴影、大面积高饱和颜色和无意义动画。
- 禁止通过 CSS 隐藏、裁掉、移出视口或禁用任何现有业务能力。

## Style-only Boundary

- Vue SFC 只允许修改 `<style>`。
- legacy/admin HTML 只允许修改现有 `<style>`。
- CSS 可以修改，但 selector 必须作用于现有 DOM。
- Router、API、Store、Service、static JavaScript、后端、数据库、配置和依赖全部冻结。

