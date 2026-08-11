# Frontend V3 Workbench Visual Contract

> Status: approved visual baseline, frozen by Task 2 on 2026-08-10. Production Vue/CSS adoption begins in Task 3 only.

## Product and audience

The product is an internal quality-operations workbench for engineers and test operators. Its single job is to make system state, execution quality, exceptions, and the next safe action legible at a glance without reducing data density.

## Source of truth

- Baseline image: `docs/frontend-v2/visual-baseline/workbench-v1-v2-hybrid.png`
- Canvas: `1920 × 1080`
- SHA-256: `369C441945CEE1AFA3E3295A01951EC2E281369825668BDBACF3B8E2E1472263`
- Approved direction: scheme 1 navigation hierarchy plus scheme 2 light workspace, thin borders, and restrained blue.

If implementation and prose conflict, this contract decides tokens and behavior; the image decides composition and visual weight. Real business data and accessible behavior take precedence over demo content in the image.

## Design thesis

The signature is an **operational spine**: a full-height deep-navy navigation rail anchors the product while an almost shadowless, cool-white workspace keeps dense execution data calm. The status rail is a continuation of that spine, not a row of decorative KPI cards.

The intentional aesthetic risk is the strong dark/light split. No second visual stunt is allowed. Charts, tables, badges, and actions stay quiet so the interface reads as an instrument panel rather than a SaaS template.

## Locked palette

| Role | Value | Required foundation token |
|---|---:|---|
| Sidebar foundation | `#132238` | `--v2-color-navy-950` |
| Sidebar active surface | `#223b5b` | `--v2-color-navy-800` |
| Primary action | `#2457ad` | `--v2-color-blue-700` |
| Navigation indicator | `#5b8ff0` | `--v2-color-blue-500` |
| Workspace canvas | `#f5f8fc` | `--v2-color-canvas-cool` |
| Panel border | `#dbe3ed` | `--v2-color-border-cool` |

White surfaces, ink text, success, warning, and danger continue to use existing semantic tokens. The six locked values above may appear literally only in `tokens.foundation.css`; consumers must use `--v2-*` aliases.

Required semantic aliases:

```css
--v2-surface-workspace: var(--v2-color-canvas-cool);
--v2-surface-sidebar: var(--v2-color-navy-950);
--v2-action-primary: var(--v2-color-blue-700);
--v2-border-panel: var(--v2-color-border-cool);
```

## Typography

- Display and page titles: `"Segoe UI Variable Display", "PingFang SC", "Microsoft YaHei UI", sans-serif`; use sparingly at 24px/700.
- Body and controls: `"Segoe UI Variable Text", "PingFang SC", "Microsoft YaHei UI", sans-serif`; 12–14px with 400–600 weights.
- IDs, timestamps, endpoints, and numeric metrics: `ui-monospace, "SFMono-Regular", Consolas, monospace`; tabular numerals required where columns align.
- External web fonts are prohibited. Typography must remain stable offline and on the existing Windows deployment.
- Uppercase letter-spacing is limited to the small English brand subtitle. Chinese navigation and controls must not use decorative tracking.

## Layout contract

```text
┌──────── 232px operational spine ────────┬──────────── 62px topbar ────────────┐
│ brand                                    │ breadcrumb  command search  account │
│ project context                          ├───────────────────────────────────────┤
│ grouped navigation                       │ page title                 actions   │
│                                          │ status rail                           │
│                                          │ trend / work area    attention queue  │
│                                          │ dense execution table                 │
│ signed-in operator                       │                                       │
└──────────────────────────────────────────┴───────────────────────────────────────┘
```

- Sidebar width: exactly `232px` on desktop via `--v2-shell-sidebar-width`.
- Topbar height: exactly `62px` via `--v2-shell-topbar-height`.
- Content canvas: `--v2-surface-workspace`.
- Panel border: `1px solid var(--v2-border-panel)`.
- Panel radius: exactly `8px` via `--v2-panel-radius`.
- Panel shadow: `0 1px 2px rgba(25, 48, 78, 0.025)` at most; panels may use no shadow.
- Primary content padding: 28px desktop, 20px compact desktop, 16px tablet/mobile.
- Main vertical rhythm: 14px between data panels; 24px between distinct page sections.
- Tables stay dense: 34px header, 43–44px body rows. Do not turn table rows into cards.

Required component declarations:

```css
--v2-layout-sidebar: 232px;
--v2-layout-topbar: 62px;
--v2-radius-panel: 8px;
--v2-shadow-panel: 0 1px 2px rgba(25, 48, 78, 0.025);
--v2-shell-sidebar-width: var(--v2-layout-sidebar);
--v2-shell-topbar-height: var(--v2-layout-topbar);
--v2-panel-radius: var(--v2-radius-panel);
--v2-panel-shadow: var(--v2-shadow-panel);
```

The exact values live in Foundation tokens. Component tokens must reference the lower layer; duplicating literals in `tokens.component.css` is prohibited by the existing V2 architecture.

## Responsive behavior

- `1440–1920px`: fixed 232px sidebar, full topbar search, two-column overview.
- `1240–1439px`: same sidebar, narrower attention queue and compact table actions.
- `1080–1239px`: sidebar may collapse into a dismissible drawer; labels remain available and must not become an icon-only mystery rail.
- Below 1080px: content becomes one column, tables use contained horizontal scrolling, and no page-level horizontal overflow is allowed.
- Focus remains visible at every width. Reduced-motion preference disables nonessential transitions.

## Interaction and copy

- Controls use direct verbs: “新建执行”, “查看”, “配置”, “重试”, “保存更改”. Do not use marketing copy.
- A button label and its success toast use the same verb.
- Empty states explain the next valid action. Errors state what failed and provide a recovery action when one exists.
- Motion is limited to 120–180ms state transitions, dropdown positioning, and functional loading feedback.

## Prohibited patterns

- Decorative linear, radial, conic, mesh, aurora, or brand gradients. `BaseSkeleton.vue` may retain its functional loading gradient.
- `backdrop-filter`, glass surfaces, translucent floating chrome, and blurred backgrounds.
- Literal locked-palette colors outside `tokens.foundation.css`.
- Component custom properties without the `--v2-` prefix.
- Panel/card shadow blur greater than 8px. Dropdown and modal overlays may use existing overlay shadow tokens; raw overlay shadows are prohibited.
- Radius greater than 10px for panels. `999px` is reserved for status chips, badges, and avatars, never content cards.
- Floating decorative shapes, oversized hero numbers, gradient metric cards, or equal-weight “card salad”.
- Emoji as interface icons. Use the existing local SVG approach; no icon dependency is added.
- Fake trend, queue, metric, or execution data in production.

## Review checklist

- The screen still reads as a test-operations instrument when branding text is hidden.
- One dark operational spine is the only dominant visual gesture.
- Borders and whitespace, not shadows, establish hierarchy.
- State is never communicated by color alone.
- Charts and metrics explain real data and degrade honestly when data is sparse.
- Keyboard focus, hover, active, disabled, loading, empty, and error states are all visible.
- No production page imports legacy CSS classes or bypasses V2 tokens.
