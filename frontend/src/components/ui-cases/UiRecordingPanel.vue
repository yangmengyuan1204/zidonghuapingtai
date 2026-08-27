<template>
  <div class="v2-ui-recording">
    <section class="v2-ui-recording__summary">
      <WorkbenchStatus tone="warning" label="录制中" detail="请在弹出的浏览器中完成操作" />
      <dl class="v2-ui-recording__facts">
        <div><dt>事件数</dt><dd>{{ session.count || 0 }}</dd></div>
        <div><dt>当前 URL</dt><dd>{{ session.current_url || session.start_url || '-' }}</dd></div>
      </dl>
    </section>

    <div class="v2-ui-recording__table-wrap">
      <table class="v2-ui-recording__table">
        <thead><tr><th>#</th><th>步骤</th><th>动作</th><th>定位质量</th><th>定位器</th><th>值</th></tr></thead>
        <tbody>
          <tr v-for="(step, index) in rows" :key="index">
            <td>{{ index + 1 }}</td>
            <td>{{ step.name || step.action || '-' }}</td>
            <td>{{ step.action || '-' }}</td>
            <td><span class="badge" :class="qualityTone(step)">{{ qualityText(step) }}</span></td>
            <td>{{ shortValue(step.locator) }}</td>
            <td>{{ shortValue(step.value) }}</td>
          </tr>
          <tr v-if="!rows.length"><td colspan="6" class="v2-ui-recording__empty">等待操作事件…</td></tr>
        </tbody>
      </table>
    </div>

    <div class="v2-ui-recording__actions">
      <BaseButton variant="secondary" type="button" @click="emit('cancel')">取消录制</BaseButton>
      <BaseButton type="button" @click="emit('save')">停止并检查</BaseButton>
    </div>
  </div>
</template>

<script setup>
import { BaseButton } from '../v2/base/index.js'
import { WorkbenchStatus } from '../v2/workbench/index.js'

defineProps({
  session: { type: Object, default: () => ({}) },
  rows: { type: Array, default: () => [] },
})

const emit = defineEmits(['cancel', 'save'])
const shortValue = (value) => {
  const text = String(value ?? '')
  return text.length > 72 ? `${text.slice(0, 72)}…` : (text || '-')
}
const qualityValue = (step) => step?.locator_profile?.quality || (step?.locator ? 'weak' : '-')
const qualityText = (step) => ({ stable: '稳定', weak: '偏弱', risk: '高风险' }[qualityValue(step)] || '-')
const qualityTone = (step) => ({ stable: 'ok', weak: 'warn', risk: 'fail' }[qualityValue(step)] || '')
</script>

<style scoped>
.v2-ui-recording {
  display: grid;
  gap: var(--v2-space-3);
}

.v2-ui-recording__summary {
  display: grid;
  gap: var(--v2-space-2);
  padding: var(--v2-space-3);
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-panel);
  background: var(--v2-surface-workspace);
}

.v2-ui-recording__facts {
  display: grid;
  grid-template-columns: minmax(96px, .3fr) minmax(0, 1fr);
  gap: var(--v2-space-2);
  margin: 0;
}

.v2-ui-recording__facts div {
  min-width: 0;
}

.v2-ui-recording__facts dt {
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-tiny);
}

.v2-ui-recording__facts dd {
  margin: var(--v2-space-micro) 0 0;
  overflow: hidden;
  color: var(--v2-text-secondary);
  font-size: var(--v2-font-size-caption);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.v2-ui-recording__table-wrap {
  max-width: 100%;
  overflow-x: auto;
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-panel);
}

.v2-ui-recording__table {
  width: 100%;
  min-width: 680px;
  border-spacing: 0;
  color: var(--v2-text-secondary);
  font-size: var(--v2-font-size-caption);
  text-align: left;
}

.v2-ui-recording__table th,
.v2-ui-recording__table td {
  padding: var(--v2-space-2);
  border-bottom: var(--v2-border-width) solid var(--v2-border-panel);
}

.v2-ui-recording__table th {
  background: var(--v2-surface-soft);
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-tiny);
}

.v2-ui-recording__empty {
  padding: var(--v2-space-5);
  color: var(--v2-text-muted);
  text-align: center;
}

.v2-ui-recording__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--v2-space-2);
}
</style>
