# Frontend Visual Coherence Design

## Objective

Improve the complete test platform's visual coherence without changing any feature, route, API, data structure, field, button, event handler, dialog behavior, permission rule, or business workflow.

The platform is an internal quality-operations workbench for test engineers and operators. Its visual job is to make configuration, execution state, data density, and the next available action easy to scan for long periods.

## Approved approach

Use a shared visual-foundation correction rather than page-by-page template reconstruction. Vue and legacy pages keep their current DOM and behavior. Typography, layout proportions, surfaces, borders, and shared components are corrected through tokens and style-only component regions.

## Visual direction

The interface uses a calm cool-grey-blue workspace with a restrained cobalt operational accent. It must not resemble a generic white SaaS dashboard, a warm beige editorial theme, or a dark icon-heavy admin template.

The signature is a quiet slate navigation spine paired with a clearly layered work canvas. Navigation contains no menu icons. A single cobalt edge marks the current page; decorative dots, gradients, glass effects, large shadows, and card clutter are prohibited.

## Color system

| Role | Value | Purpose |
|---|---:|---|
| Workspace canvas | `#E8EEF5` | Separates the application background from white working surfaces |
| Sidebar surface | `#C9D9E7` | Creates a visible but calm navigation spine |
| Panel surface | `#FFFFFF` | Primary working surface |
| Section surface | `#DDE7F0` | Page titles and major section identity |
| Utility surface | `#E7EEF4` | Filters, panel headers, and table headers |
| Context surface | `#D5E3EF` | Selected navigation and contextual controls |
| Strong border | `#B9C8D6` | Separates major surfaces |
| Soft border | `#D1DCE6` | Separates rows and minor regions |
| Primary text | `#172B3F` | Headings and high-priority content |
| Secondary text | `#50677C` | Body copy and navigation |
| Muted text | `#6C8092` | Supporting copy and labels |
| Primary action | `#245FA8` | Main buttons, focus, and active edge |

Success, warning, and danger colors retain their existing semantic meaning. Color is never the only carrier of status.

## Typography

- All Chinese interface text uses `"Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif`.
- Serif faces are removed from application headings.
- Page title: `24px`, weight `700`, line height `1.25`.
- Section title: `15px`, weight `600`.
- Navigation item: `14px`, weight `500`.
- Navigation group label: `11px`, weight `600`; no decorative letter spacing for Chinese.
- Body and controls: `14px`, weight `400` or `500`.
- Table body: `13px`; table header: `12px`, weight `600`.
- Supporting text never drops below `12px`.
- Monospace is limited to IDs, timestamps, URLs, endpoints, and structured values.
- English eyebrow labels are optional and must not be added to pages that do not already contain them.

## Layout and rhythm

- Desktop sidebar width: `220px`.
- Topbar height: `56px`.
- Main content maximum width: `1560px`, centered on wide screens.
- Desktop content padding: `24px 28px`; compact desktop: `20px`; mobile: `16px`.
- Major page-section gap: `20px`; related panel gap: `12px`.
- Page header target height: `88px`, not a hero banner.
- Panel radius: `8px`; shadows are removed or limited to a one-pixel elevation cue.
- Table header height: `38px`; body rows: `46px` minimum.
- Tables remain tables and may scroll inside their own container. Rows are never converted into cards.
- Empty space must be bounded by content width and purposeful grouping rather than full-screen stretching.

## Shell

- Sidebar uses the approved slate surface and contains no menu icons.
- Brand area is compact and aligned with the navigation text column.
- Group labels have sufficient size and separation to organize the menu without becoming visual decoration.
- Active navigation uses a contextual blue surface plus one `3px` cobalt left edge. The existing decorative right-side dot is removed visually.
- Hover is quieter than active state.
- Topbar and workspace are visually separated by a strong border, not a shadow.
- Existing project selector, AI configuration, logout, breadcrumb, and account controls keep their current behavior and labels.

## Shared workbench surfaces

- Page headers use the section surface and one cobalt edge.
- Panels use a white body, utility-colored header, strong outer border, and soft internal separators.
- Filter areas use the utility surface so controls belong to the panel rather than floating in blank space.
- Table headers use the utility surface consistently in both `AppTable` and `BaseTable`.
- Buttons retain their current variants and actions; only visual tokens such as height, radius, font weight, and color are normalized.

## Legacy/Vue coexistence

The legacy application and Vue application currently load overlapping global CSS. The implementation must address cascade precedence explicitly:

- V2 component rules must not silently lose to unlayered legacy element selectors.
- Legacy embedded pages receive equivalent typography and surface values through the existing `html.v3-embed` scope.
- No selector may hide, remove, disable, reorder, or synthesize functional controls.
- No JavaScript, API module, router, store, backend file, or migration configuration is modified.

## Files allowed for implementation

- `frontend/src/styles/v2/tokens.foundation.css`: typography scale, spacing, layout, and literal palette values.
- `frontend/src/styles/v2/tokens.semantic.css`: semantic surface, text, border, and action aliases.
- `frontend/src/styles/v2/tokens.component.css`: shell, panel, page-header, table, and control mappings.
- `frontend/src/components/AppShell.vue`: style region only.
- `frontend/src/components/v2/workbench/WorkbenchPageHeader.vue`: style region only.
- `frontend/src/components/v2/workbench/WorkbenchPanel.vue`: style region only.
- `frontend/src/components/AppTable.vue`: style region only.
- `frontend/src/components/v2/base/BaseTable.vue`: style region only.
- `static/styles.css`: existing A3/V3 visual override region only.

No view template or script file is allowed in this implementation.

## Functional freeze acceptance

- Template and script regions of every Vue component remain byte-for-byte unchanged.
- No route, navigation key, permission key, API call, request payload, response mapping, storage key, field, control, or event binding changes.
- Existing migration and parity validators retain their pre-task result; this task must introduce no new validator failure.
- Vue production build succeeds.
- The served `/v3/` bundle contains the new visual tokens and component styles.
- `git diff --check` reports no new formatting error in the allowed files.

## Visual acceptance

- No warm beige remains in page headers, panel headers, filter bars, or table headers.
- Chinese text reads as one modern sans-serif system across sidebar, Vue pages, and embedded legacy pages.
- At 1920px the content no longer stretches without restraint; major working surfaces remain centered and readable.
- Sidebar, canvas, section headers, utility regions, and panels are visibly distinct without gradients, icons, or heavy shadows.
- API cases, projects, UI cases, records, users, data factory, requirement verification, and system regression read as one product.

## Out of scope

- No new feature or component behavior.
- No page-specific information architecture redesign.
- No icon additions.
- No copy rewriting except removal of purely visual CSS-generated content if it does not exist in the DOM; existing visible labels remain unchanged.
- No backend, database, configuration, dependency, or build-system change.
