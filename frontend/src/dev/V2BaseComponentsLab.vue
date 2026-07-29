<template>
  <main class="v2-lab">
    <header class="v2-lab__header">
      <div>
        <p class="v2-lab__eyebrow">Local development only</p>
        <h1 class="v2-lab__title">Frontend V2 Base Components</h1>
        <p class="v2-lab__intro">
          Phase 5.2A + 5.2B1 独立人工验收页，不连接 Router、Pinia 或后端 API。
        </p>
      </div>
      <BaseBadge tone="info" dot>12 base components ready</BaseBadge>
    </header>

    <section class="v2-lab__section" aria-labelledby="lab-buttons">
      <div class="v2-lab__section-heading">
        <h2 id="lab-buttons">BaseButton</h2>
        <span>clicks: {{ buttonClicks }}</span>
      </div>
      <div class="v2-lab__row">
        <BaseButton data-testid="button-primary" @click="buttonClicks += 1">Primary</BaseButton>
        <BaseButton variant="secondary">Secondary</BaseButton>
        <BaseButton variant="ghost">Ghost</BaseButton>
        <BaseButton variant="danger">Danger</BaseButton>
        <BaseButton size="compact">Compact</BaseButton>
        <BaseButton disabled data-testid="button-disabled">Disabled</BaseButton>
        <BaseButton loading data-testid="button-loading">Loading action</BaseButton>
        <BaseButton variant="secondary">
          <template #icon><LabIcon /></template>
          Icon + Text
        </BaseButton>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-icon-buttons">
      <div class="v2-lab__section-heading">
        <h2 id="lab-icon-buttons">BaseIconButton</h2>
        <span>clicks: {{ iconButtonClicks }}</span>
      </div>
      <div class="v2-lab__row">
        <BaseIconButton
          label="打开搜索"
          data-testid="icon-button-default"
          @click="iconButtonClicks += 1"
        >
          <LabIcon />
        </BaseIconButton>
        <BaseIconButton
          label="固定筛选"
          variant="secondary"
          :pressed="iconPressed"
          data-testid="icon-button-pressed"
          @click="toggleIconPressed"
        >
          <LabIcon />
        </BaseIconButton>
        <BaseIconButton label="不可用操作" disabled data-testid="icon-button-disabled">
          <LabIcon />
        </BaseIconButton>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-inputs">
      <div class="v2-lab__section-heading">
        <h2 id="lab-inputs">BaseInput</h2>
        <span>native input semantics</span>
      </div>
      <div class="v2-lab__grid">
        <BaseInput v-model="normalInput" label="Normal" placeholder="输入内容" />
        <BaseInput v-model="labeledInput" label="With Label" required />
        <BaseInput v-model="prefixInput" label="Prefix" help="支持按名称搜索">
          <template #prefix><LabIcon /></template>
        </BaseInput>
        <BaseInput v-model="suffixInput" label="Suffix">
          <template #suffix><span>.json</span></template>
        </BaseInput>
        <BaseInput
          v-model="errorInput"
          label="Error"
          error="请输入有效的用例名称"
          data-testid="input-error"
        />
        <BaseInput model-value="不可编辑" label="Disabled" disabled />
        <BaseInput model-value="只读内容" label="Readonly" readonly />
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-checkboxes">
      <div class="v2-lab__section-heading">
        <h2 id="lab-checkboxes">BaseCheckbox</h2>
        <span>checked: {{ checkboxValue }}</span>
      </div>
      <div class="v2-lab__stack">
        <BaseCheckbox
          v-model="checkboxValue"
          label="Unchecked / Checked"
          data-testid="checkbox-toggle"
        />
        <BaseCheckbox model-value label="Checked" />
        <BaseCheckbox
          v-model="indeterminateValue"
          label="Indeterminate"
          indeterminate
          data-testid="checkbox-indeterminate"
        />
        <BaseCheckbox model-value label="Disabled" disabled />
        <BaseCheckbox
          v-model="describedCheckbox"
          label="With description"
          description="Space 键应切换原生 checkbox 状态"
        />
        <BaseCheckbox
          v-model="labelOnlyCheckbox"
          id="lab-checkbox-aria"
          aria-label="仅复选框示例"
          data-testid="checkbox-aria-label"
        />
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-badges">
      <div class="v2-lab__section-heading">
        <h2 id="lab-badges">BaseBadge</h2>
        <span>status display only</span>
      </div>
      <div class="v2-lab__row">
        <BaseBadge>Neutral</BaseBadge>
        <BaseBadge tone="success">Success</BaseBadge>
        <BaseBadge tone="warning">Warning</BaseBadge>
        <BaseBadge tone="danger">Danger</BaseBadge>
        <BaseBadge tone="info">Info</BaseBadge>
        <BaseBadge tone="success" dot>Operational</BaseBadge>
        <BaseBadge size="compact">Compact</BaseBadge>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-chips">
      <div class="v2-lab__section-heading">
        <h2 id="lab-chips">BaseChip</h2>
        <span>select events: {{ chipSelectCount }}</span>
      </div>
      <div class="v2-lab__row">
        <BaseChip
          :selected="chipSelected"
          data-testid="chip-toggle"
          @select="toggleChip"
        >
          Default
        </BaseChip>
        <BaseChip selected>Selected</BaseChip>
        <BaseChip count="18">
          <template #icon><LabIcon /></template>
          Count
        </BaseChip>
        <BaseChip disabled data-testid="chip-disabled">Disabled</BaseChip>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-cards">
      <div class="v2-lab__section-heading">
        <h2 id="lab-cards">BaseCard</h2>
        <span>activations: {{ cardActivations }}</span>
      </div>
      <div class="v2-lab__grid">
        <BaseCard>
          <template #header><strong>Surface</strong></template>
          默认 Surface Card
          <template #footer><small>Default padding</small></template>
        </BaseCard>
        <BaseCard variant="soft">
          <template #header><strong>Soft</strong></template>
          柔和背景容器
        </BaseCard>
        <BaseCard padding="compact">
          <strong>Compact</strong>
        </BaseCard>
        <BaseCard padding="spacious">
          <strong>Spacious</strong>
          <span>更宽松的内容间距</span>
        </BaseCard>
        <BaseCard
          as="article"
          interactive
          data-testid="card-interactive"
          @activate="cardActivations += 1"
        >
          <template #header><strong>Interactive</strong></template>
          使用 Tab 聚焦，Enter 或 Space 激活。
        </BaseCard>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-pagination">
      <div class="v2-lab__section-heading">
        <h2 id="lab-pagination">BasePagination</h2>
        <span>change events: {{ paginationEvents }}</span>
      </div>
      <div class="v2-lab__showcase-grid">
        <div class="v2-lab__example">
          <strong>Single page</strong>
          <BasePagination :page="1" :total="0" :page-size="20" aria-label="单页分页" />
        </div>
        <div class="v2-lab__example">
          <strong>Few pages</strong>
          <BasePagination :page="2" :total="50" :page-size="10" aria-label="少量页分页" />
        </div>
        <div class="v2-lab__example">
          <strong>Near start / First</strong>
          <BasePagination :page="2" :total="1000" :page-size="10" aria-label="靠前分页" />
          <BasePagination
            :page="1"
            :total="1000"
            :page-size="10"
            aria-label="第一页分页"
            data-testid="pagination-first"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Center / Interactive</strong>
          <BasePagination
            :page="paginationPage"
            :total="1000"
            :page-size="10"
            aria-label="交互分页"
            data-testid="pagination-interactive"
            @change="handlePaginationChange"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Near end / Last</strong>
          <BasePagination :page="99" :total="1000" :page-size="10" aria-label="靠后分页" />
          <BasePagination
            :page="100"
            :total="1000"
            :page-size="10"
            aria-label="最后一页分页"
            data-testid="pagination-last"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Disabled</strong>
          <BasePagination
            :page="50"
            :total="1000"
            :page-size="10"
            disabled
            aria-label="禁用分页"
            data-testid="pagination-disabled"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Huge total</strong>
          <BasePagination
            :page="500000"
            :total="10000000"
            :page-size="10"
            aria-label="超大分页"
            data-testid="pagination-huge"
          />
        </div>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-tooltips">
      <div class="v2-lab__section-heading">
        <h2 id="lab-tooltips">BaseTooltip</h2>
        <span>hover, focus, blur and Escape</span>
      </div>
      <div class="v2-lab__row v2-lab__tooltip-row">
        <BaseTooltip content="Top tooltip" placement="top" :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-top-trigger">
            Top
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip content="Right tooltip" placement="right" :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-right-trigger">
            Right
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip content="Bottom tooltip" placement="bottom" :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-bottom-trigger">
            Bottom
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip content="Left tooltip" placement="left" :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-left-trigger">
            Left
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip content="Keyboard focus tooltip" :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-keyboard-trigger">
            Keyboard focus
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip content="Disabled tooltip" disabled :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-disabled-trigger">
            Disabled tooltip
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip content="" :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-empty-trigger">
            Empty content
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip v-if="showUnmountTooltip" content="Pending unmount" :delay="1000">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-unmount-trigger">
            Unmount timer
          </BaseButton>
        </BaseTooltip>
        <BaseButton
          variant="ghost"
          size="compact"
          data-testid="tooltip-unmount-control"
          @click="showUnmountTooltip = false"
        >
          Unmount pending tooltip
        </BaseButton>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-skeletons">
      <div class="v2-lab__section-heading">
        <h2 id="lab-skeletons">BaseSkeleton</h2>
        <span>decorative loading placeholders</span>
      </div>
      <div class="v2-lab__grid">
        <div class="v2-lab__example">
          <strong>Text</strong>
          <BaseSkeleton width="80%" data-testid="skeleton-text" />
        </div>
        <div class="v2-lab__example">
          <strong>Multiple lines</strong>
          <BaseSkeleton :lines="4" data-testid="skeleton-lines" />
        </div>
        <div class="v2-lab__example">
          <strong>Circle</strong>
          <BaseSkeleton variant="circle" :width="48" data-testid="skeleton-circle" />
        </div>
        <div class="v2-lab__example">
          <strong>Rectangle</strong>
          <BaseSkeleton variant="rectangle" data-testid="skeleton-rectangle" />
        </div>
        <div class="v2-lab__example">
          <strong>Custom dimensions</strong>
          <BaseSkeleton
            variant="rectangle"
            width="70%"
            :height="72"
            data-testid="skeleton-custom"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Non-animated</strong>
          <BaseSkeleton
            variant="rectangle"
            :animated="false"
            data-testid="skeleton-static"
          />
        </div>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-empty-states">
      <div class="v2-lab__section-heading">
        <h2 id="lab-empty-states">BaseEmptyState</h2>
        <span>actions: {{ emptyActionCount }}</span>
      </div>
      <div class="v2-lab__grid">
        <BaseCard padding="none">
          <BaseEmptyState title="暂无数据" description="创建第一条记录后会显示在这里。">
            <template #icon><LabIcon /></template>
          </BaseEmptyState>
        </BaseCard>
        <BaseCard padding="none">
          <BaseEmptyState compact title="紧凑空状态" description="适用于较小容器。">
            <template #icon><LabIcon /></template>
          </BaseEmptyState>
        </BaseCard>
        <BaseCard padding="none">
          <BaseEmptyState title="未找到匹配结果" description="请调整搜索词或筛选条件。">
            <template #icon><LabIcon /></template>
          </BaseEmptyState>
        </BaseCard>
        <BaseCard padding="none">
          <BaseEmptyState
            title="还没有测试用例"
            description="创建用例以开始自动化验证。"
            data-testid="empty-with-action"
          >
            <template #icon><LabIcon /></template>
            <template #action>
              <BaseButton
                size="compact"
                data-testid="empty-action"
                @click="emptyActionCount += 1"
              >
                创建用例
              </BaseButton>
            </template>
          </BaseEmptyState>
        </BaseCard>
        <BaseCard padding="none">
          <BaseEmptyState
            title="无操作空状态"
            description="此状态不渲染空 action 容器。"
            icon-hidden
            data-testid="empty-without-action"
          />
        </BaseCard>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-error-states">
      <div class="v2-lab__section-heading">
        <h2 id="lab-error-states">BaseErrorState</h2>
        <span>retry events: {{ retryCount }}</span>
      </div>
      <div class="v2-lab__grid">
        <BaseCard padding="none">
          <BaseErrorState
            title="加载失败"
            message="暂时无法获取数据，请稍后重试。"
            retryable
            data-testid="error-retryable"
            @retry="retryCount += 1"
          >
            <template #icon><LabIcon /></template>
          </BaseErrorState>
        </BaseCard>
        <BaseCard padding="none">
          <BaseErrorState
            title="不可恢复错误"
            message="请联系管理员处理。"
            data-testid="error-non-retryable"
          />
        </BaseCard>
        <BaseCard padding="none">
          <BaseErrorState
            title="正在重试"
            message="正在重新连接服务。"
            retryable
            busy
            data-testid="error-busy"
            @retry="retryCount += 1"
          />
        </BaseCard>
        <BaseCard padding="none">
          <BaseErrorState
            compact
            title="紧凑错误状态"
            message="适用于较小容器。"
          />
        </BaseCard>
        <BaseCard padding="none">
          <BaseErrorState
            title="需要其他操作"
            message="使用调用方提供的自定义 action。"
            retryable
            data-testid="error-custom-action"
          >
            <template #action>
              <BaseButton variant="secondary" size="compact">查看帮助</BaseButton>
            </template>
          </BaseErrorState>
        </BaseCard>
        <BaseCard padding="none">
          <BaseErrorState
            title="含错误详情"
            message="可读详情保持为普通内容。"
            data-testid="error-details"
          >
            <template #details>Request ID: demo-request</template>
          </BaseErrorState>
        </BaseCard>
      </div>
    </section>

    <output class="v2-lab__status" aria-live="polite" data-testid="lab-status">
      Button {{ buttonClicks }} · Icon {{ iconButtonClicks }} · Chip {{ chipSelectCount }} ·
      Card {{ cardActivations }} · Pagination {{ paginationEvents }} ·
      Empty {{ emptyActionCount }} · Retry {{ retryCount }}
    </output>
  </main>
</template>

<script setup>
import { defineComponent, h, ref } from 'vue'
import {
  BaseBadge,
  BaseButton,
  BaseCard,
  BaseCheckbox,
  BaseChip,
  BaseEmptyState,
  BaseErrorState,
  BaseIconButton,
  BaseInput,
  BasePagination,
  BaseSkeleton,
  BaseTooltip,
} from '../components/v2/base/index.js'

const LabIcon = defineComponent({
  name: 'LabIcon',
  setup() {
    return () => h(
      'svg',
      { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2' },
      [
        h('circle', { cx: '11', cy: '11', r: '7' }),
        h('path', { d: 'm16 16 4 4' }),
      ],
    )
  },
})

const buttonClicks = ref(0)
const iconButtonClicks = ref(0)
const iconPressed = ref(true)
const chipSelected = ref(false)
const chipSelectCount = ref(0)
const cardActivations = ref(0)
const normalInput = ref('')
const labeledInput = ref('已有内容')
const prefixInput = ref('')
const suffixInput = ref('contract')
const errorInput = ref('')
const checkboxValue = ref(false)
const indeterminateValue = ref(false)
const describedCheckbox = ref(false)
const labelOnlyCheckbox = ref(false)
const paginationPage = ref(50)
const paginationEvents = ref(0)
const emptyActionCount = ref(0)
const retryCount = ref(0)
const showUnmountTooltip = ref(true)

function toggleIconPressed() {
  iconButtonClicks.value += 1
  iconPressed.value = !iconPressed.value
}

function toggleChip() {
  chipSelectCount.value += 1
  chipSelected.value = !chipSelected.value
}

function handlePaginationChange(nextPage) {
  paginationEvents.value += 1
  paginationPage.value = nextPage
}
</script>

<style scoped>
@layer v2-utilities {
  .v2-lab {
    min-height: 100vh;
    padding: var(--v2-space-5);
    color: var(--v2-text-primary);
    background: var(--v2-surface-canvas);
  }

  .v2-lab__header {
    max-width: var(--v2-layout-workspace-max);
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--v2-space-4);
    margin: 0 auto var(--v2-space-5);
  }

  .v2-lab__eyebrow,
  .v2-lab__intro,
  .v2-lab__section-heading span,
  .v2-lab__status {
    color: var(--v2-text-muted);
  }

  .v2-lab__eyebrow {
    margin: 0 0 var(--v2-space-1);
    font-size: var(--v2-font-size-tiny);
    font-weight: var(--v2-font-weight-bold);
    letter-spacing: var(--v2-letter-spacing-wide);
    text-transform: uppercase;
  }

  .v2-lab__title {
    margin: 0;
    font-size: var(--v2-font-size-display);
    line-height: var(--v2-line-height-tight);
  }

  .v2-lab__intro {
    margin: var(--v2-space-2) 0 0;
  }

  .v2-lab__section {
    max-width: var(--v2-layout-workspace-max);
    padding: var(--v2-space-4);
    margin: 0 auto var(--v2-space-3);
    background: var(--v2-surface-default);
    border: var(--v2-border-width) solid var(--v2-border-default);
    border-radius: var(--v2-radius-md);
  }

  .v2-lab__section-heading {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--v2-space-3);
    margin-bottom: var(--v2-space-3);
  }

  .v2-lab__section-heading h2 {
    margin: 0;
    font-size: var(--v2-font-size-section);
  }

  .v2-lab__section-heading span,
  .v2-lab__status {
    font-size: var(--v2-font-size-caption);
  }

  .v2-lab__row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--v2-space-2);
  }

  .v2-lab__grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(calc(var(--v2-space-7) * 4), 1fr));
    gap: var(--v2-space-3);
  }

  .v2-lab__stack {
    display: grid;
    gap: var(--v2-space-2);
  }

  .v2-lab__showcase-grid {
    display: grid;
    gap: var(--v2-space-3);
  }

  .v2-lab__example {
    display: grid;
    align-content: start;
    gap: var(--v2-space-2);
    min-width: 0;
    padding: var(--v2-space-3);
    background: var(--v2-surface-soft);
    border-radius: var(--v2-radius-sm);
  }

  .v2-lab__tooltip-row {
    padding: var(--v2-space-6) var(--v2-space-4);
  }

  .v2-lab__status {
    max-width: var(--v2-layout-workspace-max);
    display: block;
    margin: var(--v2-space-4) auto 0;
    text-align: center;
  }

  @media (max-width: 1240px) {
    .v2-lab {
      padding: var(--v2-space-4);
    }
  }
}
</style>
