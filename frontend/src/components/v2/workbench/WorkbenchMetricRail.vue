<template>
  <section class="v2-workbench-metric-rail" :aria-label="ariaLabel">
    <div v-if="statusTitle || statusLabel" class="v2-workbench-metric-rail__intro">
      <span class="v2-workbench-metric-rail__kicker">{{ statusLabel }}</span>
      <strong class="v2-workbench-metric-rail__status">{{ statusTitle }}</strong>
      <span v-if="statusDetail" class="v2-workbench-metric-rail__detail">{{ statusDetail }}</span>
    </div>
    <dl class="v2-workbench-metric-rail__items">
      <div v-for="item in items" :key="item.key" class="v2-workbench-metric-rail__item">
        <dt class="v2-workbench-metric-rail__label">{{ item.label }}</dt>
        <dd class="v2-workbench-metric-rail__value">{{ item.value }}</dd>
        <span v-if="item.trend" class="v2-workbench-metric-rail__trend">{{ item.trend }}</span>
        <span
          v-if="item.progress !== undefined && item.progress !== null"
          class="v2-workbench-metric-rail__progress"
          role="progressbar"
          :aria-label="`${item.label} ${clampProgress(item.progress)}%`"
          :aria-valuenow="clampProgress(item.progress)"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <span
            class="v2-workbench-metric-rail__progress-value"
            :class="`v2-workbench-metric-rail__progress-value--${normalizeTone(item.tone)}`"
            :style="{ width: `${clampProgress(item.progress)}%` }"
          />
        </span>
      </div>
    </dl>
  </section>
</template>

<script setup>
defineProps({
  items: { type: Array, default: () => [] },
  statusTitle: { type: String, default: '' },
  statusLabel: { type: String, default: '' },
  statusDetail: { type: String, default: '' },
  ariaLabel: { type: String, default: '关键指标' },
})

const allowedTones = new Set(['neutral', 'success', 'warning', 'danger', 'info'])
const normalizeTone = (tone) => allowedTones.has(tone) ? tone : 'neutral'
const clampProgress = (value) => Math.min(100, Math.max(0, Number(value) || 0))
</script>

<style scoped>
.v2-workbench-metric-rail {
  display: grid;
  grid-template-columns: minmax(184px, 1.15fr) minmax(0, 4fr);
  overflow: hidden;
  border: var(--v2-border-width) solid var(--v2-metric-rail-border);
  border-radius: var(--v2-radius-panel);
  background: var(--v2-metric-rail-surface);
  box-shadow: var(--v2-shadow-panel);
}

.v2-workbench-metric-rail__intro {
  display: grid;
  align-content: center;
  gap: var(--v2-space-micro);
  min-height: 104px;
  padding: var(--v2-space-3);
  border-right: var(--v2-border-width) solid var(--v2-metric-rail-border);
  background: var(--v2-metric-rail-intro-surface);
}

.v2-workbench-metric-rail__kicker {
  color: var(--v2-metric-rail-intro-text-muted);
  font-size: var(--v2-font-size-tiny);
  font-weight: var(--v2-font-weight-semibold);
  letter-spacing: var(--v2-letter-spacing-wide);
}

.v2-workbench-metric-rail__status {
  color: var(--v2-metric-rail-intro-text);
  font-family: var(--v2-font-family-display);
  font-size: var(--v2-font-size-section);
  font-weight: var(--v2-font-weight-semibold);
}

.v2-workbench-metric-rail__detail {
  color: var(--v2-metric-rail-intro-text-muted);
  font-size: var(--v2-font-size-caption);
}

.v2-workbench-metric-rail__items {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  margin: 0;
}

.v2-workbench-metric-rail__item {
  position: relative;
  display: grid;
  align-content: center;
  gap: var(--v2-space-micro);
  min-height: 104px;
  padding: var(--v2-space-3);
}

.v2-workbench-metric-rail__item + .v2-workbench-metric-rail__item {
  border-left: var(--v2-border-width) solid var(--v2-metric-rail-border);
}

.v2-workbench-metric-rail__label {
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-caption);
}

.v2-workbench-metric-rail__value {
  margin: 0;
  color: var(--v2-text-primary);
  font-family: var(--v2-font-family-display);
  font-size: var(--v2-font-size-heading);
  font-weight: var(--v2-font-weight-semibold);
  letter-spacing: var(--v2-letter-spacing-tight);
}

.v2-workbench-metric-rail__trend {
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-tiny);
}

.v2-workbench-metric-rail__progress {
  display: block;
  overflow: hidden;
  height: var(--v2-space-micro);
  margin-top: var(--v2-space-micro);
  border-radius: var(--v2-radius-round);
  background: var(--v2-surface-pressed);
}

.v2-workbench-metric-rail__progress-value {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--v2-text-muted);
  transition: width var(--v2-motion-duration-dialog) var(--v2-motion-easing-standard);
}

.v2-workbench-metric-rail__progress-value--success {
  background: var(--v2-feedback-success);
}

.v2-workbench-metric-rail__progress-value--warning {
  background: var(--v2-feedback-warning);
}

.v2-workbench-metric-rail__progress-value--danger {
  background: var(--v2-feedback-danger);
}

.v2-workbench-metric-rail__progress-value--info {
  background: var(--v2-action-primary);
}

@media (max-width: 820px) {
  .v2-workbench-metric-rail {
    grid-template-columns: 1fr;
  }

  .v2-workbench-metric-rail__intro {
    min-height: auto;
    border-right: 0;
    border-bottom: var(--v2-border-width) solid var(--v2-metric-rail-border);
  }
}

@media (prefers-reduced-motion: reduce) {
  .v2-workbench-metric-rail__progress-value {
    transition-duration: var(--v2-motion-reduced);
  }
}
</style>
