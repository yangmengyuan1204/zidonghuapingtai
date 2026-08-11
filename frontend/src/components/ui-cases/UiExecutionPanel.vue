<template>
  <div class="v2-ui-execution">
    <div class="v2-ui-execution__progress-meta">
      <strong>{{ statusText(run.status) }}</strong>
      <span>{{ percent }}%</span>
    </div>
    <div class="v2-ui-execution__progress" role="progressbar" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100">
      <span
        class="v2-ui-execution__progress-value"
        :class="{ 'v2-ui-execution__progress-value--failed': run.status === 'failed' }"
        :style="{ width: `${percent}%` }"
      />
    </div>

    <div v-if="isFinished" class="v2-ui-execution__summary">
      <div><span>执行结果</span><strong>{{ statusText(run.status) }}</strong></div>
      <div><span>记录 ID</span><strong>{{ run.record_id || '-' }}</strong></div>
      <div><span>当前步骤</span><strong>{{ run.current_step_index || 0 }} / {{ run.steps?.length || 0 }}</strong></div>
      <div><span>可见浏览器</span><strong>{{ run.headed ? '已开启' : '未开启' }}</strong></div>
    </div>
    <p v-if="run.error" class="v2-ui-execution__error">{{ run.error }}</p>

    <div class="v2-ui-execution__layout">
      <div class="v2-ui-execution__table-wrap">
        <table class="v2-ui-execution__table">
          <thead><tr><th>#</th><th>步骤</th><th>动作</th><th>定位器</th><th>状态</th><th>耗时</th><th>结果</th></tr></thead>
          <tbody>
            <tr v-for="step in steps" :key="step.index">
              <td>{{ step.index }}</td>
              <td>{{ step.name || step.action || '-' }}</td>
              <td>{{ step.action || '-' }}</td>
              <td>{{ shortValue(step.used_locator || step.locator || '-') }}</td>
              <td><WorkbenchStatus :tone="statusTone(step.status)" :label="statusText(step.status)" compact /></td>
              <td>{{ step.duration_ms ? `${step.duration_ms} ms` : '-' }}</td>
              <td>{{ stepResult(step) }}</td>
            </tr>
            <tr v-if="!steps.length"><td colspan="7" class="v2-ui-execution__empty">暂无步骤</td></tr>
          </tbody>
        </table>
      </div>

      <section class="v2-ui-execution__evidence">
        <h3>最新截图</h3>
        <img v-if="run.latest_screenshot_url" :src="run.latest_screenshot_url" alt="执行截图" />
        <p v-else>等待截图生成…</p>
      </section>
    </div>

    <details v-if="isFinished" class="v2-ui-execution__details" open>
      <summary>最终数据</summary>
      <pre>{{ extractedText }}</pre>
    </details>
    <details class="v2-ui-execution__details">
      <summary>执行事件</summary>
      <pre>{{ JSON.stringify(run.events || [], null, 2) }}</pre>
    </details>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { WorkbenchStatus } from '../v2/workbench/index.js'

const props = defineProps({
  run: { type: Object, default: () => ({}) },
  steps: { type: Array, default: () => [] },
  percent: { type: Number, default: 0 },
  extractedText: { type: String, default: '' },
  statusText: { type: Function, required: true },
  stepResult: { type: Function, required: true },
  shortValue: { type: Function, required: true },
})

const isFinished = computed(() => ['passed', 'failed'].includes(props.run.status))
const statusTone = (status) => ({ passed: 'success', failed: 'danger', running: 'info', pending: 'neutral' })[status] || 'neutral'
</script>

<style scoped>
.v2-ui-execution {
  display: grid;
  gap: var(--v2-space-3);
}

.v2-ui-execution__progress-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--v2-text-secondary);
  font-size: var(--v2-font-size-caption);
}

.v2-ui-execution__progress {
  overflow: hidden;
  height: var(--v2-space-1);
  border-radius: var(--v2-radius-round);
  background: var(--v2-surface-pressed);
}

.v2-ui-execution__progress-value {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--v2-action-primary);
  transition: width var(--v2-motion-duration-dialog) var(--v2-motion-easing-standard);
}

.v2-ui-execution__progress-value--failed {
  background: var(--v2-feedback-danger);
}

.v2-ui-execution__summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--v2-space-2);
}

.v2-ui-execution__summary div,
.v2-ui-execution__evidence,
.v2-ui-execution__details {
  padding: var(--v2-space-3);
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-panel);
  background: var(--v2-surface-workspace);
}

.v2-ui-execution__summary div {
  display: grid;
  gap: var(--v2-space-micro);
}

.v2-ui-execution__summary span {
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-tiny);
}

.v2-ui-execution__error {
  margin: 0;
  padding: var(--v2-space-2) var(--v2-space-3);
  border: var(--v2-border-width) solid var(--v2-feedback-danger);
  border-radius: var(--v2-radius-sm);
  background: var(--v2-feedback-danger-soft);
  color: var(--v2-feedback-danger);
}

.v2-ui-execution__layout {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(280px, .7fr);
  gap: var(--v2-space-3);
}

.v2-ui-execution__table-wrap {
  overflow-x: auto;
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-panel);
}

.v2-ui-execution__table {
  width: 100%;
  min-width: 760px;
  border-spacing: 0;
  color: var(--v2-text-secondary);
  font-size: var(--v2-font-size-caption);
  text-align: left;
}

.v2-ui-execution__table th,
.v2-ui-execution__table td {
  padding: var(--v2-space-2);
  border-bottom: var(--v2-border-width) solid var(--v2-border-panel);
}

.v2-ui-execution__table th {
  background: var(--v2-surface-soft);
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-tiny);
}

.v2-ui-execution__empty,
.v2-ui-execution__evidence p {
  padding: var(--v2-space-5);
  color: var(--v2-text-muted);
  text-align: center;
}

.v2-ui-execution__evidence h3 {
  margin: 0 0 var(--v2-space-2);
  font-size: var(--v2-font-size-body);
}

.v2-ui-execution__evidence img {
  width: 100%;
  max-height: calc(var(--v2-space-7) * 6.5);
  object-fit: contain;
}

.v2-ui-execution__details summary {
  cursor: pointer;
  color: var(--v2-text-secondary);
  font-weight: var(--v2-font-weight-semibold);
}

.v2-ui-execution__details pre {
  max-height: calc(var(--v2-space-7) * 4);
  overflow: auto;
  margin: var(--v2-space-2) 0 0;
  color: var(--v2-text-secondary);
  font-family: var(--v2-font-family-mono);
  font-size: var(--v2-font-size-tiny);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@media (max-width: 900px) {
  .v2-ui-execution__summary,
  .v2-ui-execution__layout {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .v2-ui-execution__progress-value {
    transition-duration: var(--v2-motion-reduced);
  }
}
</style>
