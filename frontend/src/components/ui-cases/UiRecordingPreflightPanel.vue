<template>
  <section class="v2-ui-preflight">
    <header class="v2-ui-preflight__header">
      <div>
        <strong>干净会话自动检查</strong>
        <p>
          {{ statusMessage }}
          <span v-if="totalSteps"> · {{ completedSteps }} / {{ totalSteps }}</span>
          <span v-if="verifiedRounds"> · 已通过轮次 {{ report.verified_rounds }} / {{ report.required_rounds || 2 }}</span>
        </p>
      </div>
      <span class="badge" :class="statusTone">{{ statusText }}</span>
    </header>

    <div v-if="steps.length" class="v2-ui-preflight__steps">
      <article v-for="(step, index) in steps" :key="`${step.index || index}-${step.status}`" :class="['v2-ui-preflight__step', step.status]">
        <div><strong>#{{ step.index || index + 1 }} {{ step.name || step.action || '步骤' }}</strong></div>
        <div>{{ step.status || '-' }} · {{ step.used_locator || step.locator || '-' }}</div>
        <p v-if="step.error || step.reason">{{ step.error || step.reason }}</p>
        <p v-if="step.effect || step.expected_effect">预期结果：{{ step.expected_effect || step.effect }}</p>
        <p v-if="step.actual">实际结果：{{ step.actual }}</p>
        <ul v-if="step.locator_candidates?.length" class="v2-ui-preflight__candidates">
          <li v-for="item in step.locator_candidates.slice(0, 3)" :key="item.value">
            <code>{{ item.value }}</code>
            <span>{{ item.score }} 分 · {{ (item.reasons || []).join('；') }}</span>
          </li>
        </ul>
        <code v-if="candidate(step)">推荐：{{ candidate(step) }}</code>
        <BaseButton v-if="candidate(step)" variant="secondary" type="button" @click="emit('adopt', { index: step.index || index + 1, locator: candidate(step) })">采用候选并重新检查</BaseButton>
      </article>
    </div>

    <div v-if="report.screenshot" class="v2-ui-preflight__evidence">
      <span>失败截图：{{ report.screenshot }}</span>
    </div>
    <div v-if="report.current_url" class="v2-ui-preflight__evidence">当前 URL：{{ report.current_url }}</div>
    <div v-if="props.preflight?.error_category || report.error_category" class="v2-ui-preflight__evidence">
      失败分类：{{ props.preflight?.error_category || report.error_category }}
    </div>

    <footer v-if="terminal" class="v2-ui-preflight__actions">
      <BaseButton v-if="failed" variant="secondary" type="button" @click="emit('retry')">重新检查</BaseButton>
      <BaseButton v-if="failed" type="button" @click="emit('save-draft')">保存待修复草稿</BaseButton>
    </footer>

    <footer v-if="paused" class="v2-ui-preflight__actions">
      <BaseButton v-if="props.preflight?.status === 'repair_required'" type="button" @click="emit('repick', failedStepIndex)">重新选点</BaseButton>
      <BaseButton v-if="props.preflight?.status === 'repair_ready'" type="button" @click="emit('restart')">从头重新验证</BaseButton>
      <BaseButton variant="secondary" type="button" @click="emit('save-draft')">保存待修复草稿</BaseButton>
    </footer>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { BaseButton } from '../v2/base/index.js'

const props = defineProps({ preflight: { type: Object, default: () => ({}) } })
const emit = defineEmits(['retry', 'save-draft', 'adopt', 'repick', 'restart'])
const report = computed(() => props.preflight?.report || {})
const steps = computed(() => report.value.steps || [])
const totalSteps = computed(() => Number(report.value.total_steps || steps.value.length || 0))
const completedSteps = computed(() => Number(report.value.completed_steps || steps.value.filter((step) => ['passed', 'failed'].includes(step.status)).length))
const failed = computed(() => props.preflight?.status === 'failed')
const terminal = computed(() => ['passed', 'failed'].includes(props.preflight?.status))
const paused = computed(() => ['repair_required', 'repick_waiting', 'repair_ready'].includes(props.preflight?.status))
const verifiedRounds = computed(() => Number(report.value.verified_rounds) > 0)
const failedStepIndex = computed(() => props.preflight?.repair?.failed_step_index || report.value.repair?.failed_step_index || 0)

const STATUS_TEXT = {
  queued: '排队中',
  resetting: '正在重置测试数据',
  round_1_running: '第一轮修复验证',
  repair_required: '需要重新选择元素',
  repick_waiting: '请在验证浏览器中点击正确元素',
  repair_ready: '已重新选择，可从头验证',
  round_2_running: '第二轮冻结验证',
  passed: '双轮验证通过',
  failed: '验证失败',
}
const statusText = computed(() => STATUS_TEXT[props.preflight?.status] || '未开始')
const statusTone = computed(() => ({ passed: 'ok', failed: 'fail', repair_required: 'warn', repick_waiting: 'warn', repair_ready: 'warn' }[props.preflight?.status] || 'warn'))
const statusMessage = computed(() => {
  if (props.preflight?.status === 'passed') return '双轮验证通过，将保存为可执行用例。'
  if (props.preflight?.status === 'repair_required') return '第一轮验证发现定位问题，请在验证浏览器中重新选择元素。'
  if (props.preflight?.status === 'repick_waiting') return '等待在验证浏览器中点击正确元素。'
  if (props.preflight?.status === 'repair_ready') return '已重新选择元素，可从数据重置开始重新验证。'
  if (props.preflight?.status === 'failed') return report.value.error || '检查失败，可重试或保存为待修复草稿。'
  return '系统正在新建浏览器并从起始 URL 完整回放。'
})
const candidate = (step) => step?.suggested_locator || step?.healed_locator || ''
</script>

<style scoped>
.v2-ui-preflight { display: grid; gap: var(--v2-space-3); margin-top: var(--v2-space-3); }
.v2-ui-preflight__header { display: flex; justify-content: space-between; gap: var(--v2-space-3); padding: var(--v2-space-3); border: var(--v2-border-width) solid var(--v2-border-panel); border-radius: var(--v2-radius-panel); background: var(--v2-surface-soft); }
.v2-ui-preflight__header p { margin: var(--v2-space-micro) 0 0; color: var(--v2-text-muted); }
.v2-ui-preflight__steps { display: grid; gap: var(--v2-space-2); max-height: 320px; overflow: auto; }
.v2-ui-preflight__step { padding: var(--v2-space-2); border-left: 3px solid var(--v2-border-panel); background: var(--v2-surface-workspace); }
.v2-ui-preflight__step.passed { border-left-color: var(--v2-color-success, #16a34a); }
.v2-ui-preflight__step.failed { border-left-color: var(--v2-color-danger, #dc2626); }
.v2-ui-preflight__step p, .v2-ui-preflight__step code { display: block; margin: var(--v2-space-micro) 0 0; color: var(--v2-text-secondary); white-space: pre-wrap; }
.v2-ui-preflight__candidates { display: grid; gap: var(--v2-space-micro); margin: var(--v2-space-1) 0 0; padding-left: var(--v2-space-4); color: var(--v2-text-muted); }
.v2-ui-preflight__candidates code { overflow-wrap: anywhere; }
.v2-ui-preflight__evidence { color: var(--v2-text-muted); font-size: var(--v2-font-size-caption); overflow-wrap: anywhere; }
.v2-ui-preflight__actions { display: flex; justify-content: flex-end; gap: var(--v2-space-2); }
</style>