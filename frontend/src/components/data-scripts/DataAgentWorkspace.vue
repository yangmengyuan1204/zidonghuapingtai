<template>
  <div class="v2-data-agent">
    <div v-if="session" class="v2-data-agent__status">
      <WorkbenchStatus :tone="sessionTone" :label="session.status || '处理中'" :detail="session.id ? `会话 ${session.id}` : ''" />
      <span v-if="session.plan_version">计划版本 {{ session.plan_version }}</span>
    </div>
    <div class="v2-data-agent__conversation">
      <BaseEmptyState v-if="!session" title="描述你要准备的测试数据" description="智能体会先理解目标并生成可确认计划，不会直接执行高风险动作。" compact icon-hidden />
      <pre v-else>{{ sessionText }}</pre>
    </div>
    <BaseTextarea
      :model-value="instruction"
      label="任务说明"
      :rows="5"
      placeholder="例如：为测试环境准备一个可退款订单，并保留订单号"
      @update:model-value="emit('update:instruction', $event)"
    />
    <div class="v2-data-agent__actions">
      <BaseButton v-if="!session" :disabled="busy" @click="emit('create')">{{ busy ? '正在理解…' : '开始规划' }}</BaseButton>
      <template v-else>
        <BaseButton variant="secondary" :disabled="busy" @click="emit('refresh')">刷新状态</BaseButton>
        <BaseButton v-if="canConfirm" :disabled="busy" @click="emit('confirm')">确认并执行</BaseButton>
        <BaseButton variant="danger" :disabled="busy" @click="emit('cancel')">取消任务</BaseButton>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { BaseButton, BaseEmptyState, BaseTextarea } from '../v2/base/index.js'
import { WorkbenchStatus } from '../v2/workbench/index.js'

const props = defineProps({
  session: { type: Object, default: null },
  instruction: { type: String, default: '' },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['update:instruction', 'create', 'refresh', 'confirm', 'cancel'])
const canConfirm = computed(() => Boolean(props.session?.plan_version) && !['completed', 'cancelled', 'failed'].includes(props.session?.status))
const sessionTone = computed(() => ({ completed: 'success', failed: 'danger', cancelled: 'neutral', waiting_risk_confirmation: 'warning' })[props.session?.status] || 'info')
const sessionText = computed(() => JSON.stringify(props.session, null, 2))
</script>

<style scoped>
.v2-data-agent {
  display: grid;
  gap: var(--v2-space-3);
  padding: var(--v2-space-3);
}

.v2-data-agent__status,
.v2-data-agent__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--v2-space-2);
}

.v2-data-agent__status > span {
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-caption);
}

.v2-data-agent__conversation {
  min-height: calc(var(--v2-space-7) * 2.5);
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-panel);
  background: var(--v2-surface-workspace);
}

.v2-data-agent__conversation pre {
  max-height: calc(var(--v2-space-7) * 5);
  overflow: auto;
  margin: 0;
  padding: var(--v2-space-3);
  color: var(--v2-text-secondary);
  font-family: var(--v2-font-family-mono);
  font-size: var(--v2-font-size-tiny);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.v2-data-agent__actions {
  justify-content: flex-end;
}
</style>
