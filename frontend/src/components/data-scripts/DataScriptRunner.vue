<template>
  <form class="v2-data-script-runner" @submit.prevent="emit('run')">
    <div class="v2-data-script-runner__heading">
      <div>
        <span>SELECTED SCRIPT</span>
        <h3>{{ script?.name || '请选择脚本' }}</h3>
      </div>
      <WorkbenchStatus v-if="script" :tone="script.risk_level === 'high' ? 'warning' : 'info'" :label="script.risk_level === 'high' ? '执行前请确认影响范围' : '标准执行'" />
    </div>
    <BaseTextarea
      :model-value="variablesText"
      label="运行变量（JSON）"
      name="variables"
      :rows="12"
      :error="error"
      help="项目、环境与变量会按现有 DataScriptExecuteRequest 提交。"
      @update:model-value="emit('update:variablesText', $event)"
    />
    <div class="v2-data-script-runner__actions">
      <BaseButton type="submit" :disabled="!script || running">{{ running ? '执行中…' : '执行脚本' }}</BaseButton>
    </div>
    <pre v-if="result" class="v2-data-script-runner__result">{{ result }}</pre>
  </form>
</template>

<script setup>
import { BaseButton, BaseTextarea } from '../v2/base/index.js'
import { WorkbenchStatus } from '../v2/workbench/index.js'

defineProps({
  script: { type: Object, default: null },
  variablesText: { type: String, default: '{}' },
  running: { type: Boolean, default: false },
  result: { type: String, default: '' },
  error: { type: String, default: '' },
})
const emit = defineEmits(['update:variablesText', 'run'])
</script>

<style scoped>
.v2-data-script-runner {
  display: grid;
  gap: var(--v2-space-3);
  padding: var(--v2-space-3);
}

.v2-data-script-runner__heading,
.v2-data-script-runner__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v2-space-3);
}

.v2-data-script-runner__heading span {
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-tiny);
  font-weight: var(--v2-font-weight-semibold);
  letter-spacing: var(--v2-letter-spacing-wide);
}

.v2-data-script-runner__heading h3 {
  margin: var(--v2-space-micro) 0 0;
  font-size: var(--v2-font-size-section);
}

.v2-data-script-runner__actions {
  justify-content: flex-end;
}

.v2-data-script-runner__result {
  max-height: calc(var(--v2-space-7) * 5);
  overflow: auto;
  margin: 0;
  padding: var(--v2-space-3);
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-sm);
  background: var(--v2-surface-workspace);
  color: var(--v2-text-secondary);
  font-family: var(--v2-font-family-mono);
  font-size: var(--v2-font-size-tiny);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
