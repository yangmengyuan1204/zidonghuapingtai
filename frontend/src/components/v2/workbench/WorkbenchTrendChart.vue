<template>
  <div class="v2-workbench-trend-chart">
    <svg
      v-if="hasData"
      class="v2-workbench-trend-chart__svg"
      viewBox="0 0 900 240"
      role="img"
      :aria-label="title"
      preserveAspectRatio="none"
    >
      <title>{{ title }}</title>
      <g class="v2-workbench-trend-chart__grid" aria-hidden="true">
        <line v-for="y in gridLines" :key="y" x1="44" :y1="y" x2="884" :y2="y" />
      </g>
      <g class="v2-workbench-trend-chart__y-label" aria-hidden="true">
        <text
          v-for="(label, index) in yAxisLabels"
          :key="label"
          x="34"
          :y="gridLines[index] + 4"
          text-anchor="end"
        >{{ label }}</text>
      </g>
      <polygon
        v-if="passedAreaPoints"
        class="v2-workbench-trend-chart__area"
        :points="passedAreaPoints"
      />
      <polyline
        v-if="passedPoints"
        class="v2-workbench-trend-chart__line v2-workbench-trend-chart__line--passed"
        :points="passedPoints"
      />
      <polyline
        v-if="failedPoints"
        class="v2-workbench-trend-chart__line v2-workbench-trend-chart__line--failed"
        :points="failedPoints"
      />
      <g aria-hidden="true">
        <circle
          v-for="(value, index) in normalizedPassed"
          :key="`passed-${index}`"
          class="v2-workbench-trend-chart__point v2-workbench-trend-chart__point--passed"
          :cx="xAt(index)"
          :cy="yAt(value)"
          r="4"
        />
        <circle
          v-for="(value, index) in normalizedFailed"
          :key="`failed-${index}`"
          class="v2-workbench-trend-chart__point v2-workbench-trend-chart__point--failed"
          :cx="xAt(index)"
          :cy="yAt(value)"
          r="3"
        />
      </g>
      <g class="v2-workbench-trend-chart__labels" aria-hidden="true">
        <text
          v-for="(label, index) in normalizedLabels"
          :key="`${label}-${index}`"
          :x="xAt(index)"
          y="228"
          text-anchor="middle"
        >{{ label }}</text>
      </g>
    </svg>
    <div v-else class="v2-workbench-trend-chart__empty" role="status">
      暂无可绘制的执行趋势
    </div>
    <div v-if="hasData" class="v2-workbench-trend-chart__legend" aria-hidden="true">
      <span class="v2-workbench-trend-chart__legend-item">
        <i class="v2-workbench-trend-chart__legend-mark v2-workbench-trend-chart__legend-mark--passed" />通过
      </span>
      <span class="v2-workbench-trend-chart__legend-item">
        <i class="v2-workbench-trend-chart__legend-mark v2-workbench-trend-chart__legend-mark--failed" />失败
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: { type: String, default: '执行趋势：通过与失败' },
  labels: { type: Array, default: () => [] },
  passed: { type: Array, default: () => [] },
  failed: { type: Array, default: () => [] },
})

const gridLines = [18, 62, 106, 150, 194]
const pointCount = computed(() => Math.min(props.labels.length, Math.max(props.passed.length, props.failed.length)))
const normalizedLabels = computed(() => props.labels.slice(0, pointCount.value))
const normalizedPassed = computed(() => props.passed.slice(0, pointCount.value).map((value) => Math.max(0, Number(value) || 0)))
const normalizedFailed = computed(() => props.failed.slice(0, pointCount.value).map((value) => Math.max(0, Number(value) || 0)))
const maximum = computed(() => Math.max(1, ...normalizedPassed.value, ...normalizedFailed.value))
const yAxisLabels = computed(() => gridLines.map((_, index) => String(Math.round(maximum.value * (4 - index) / 4))))
const hasData = computed(() => pointCount.value > 0 && (normalizedPassed.value.length || normalizedFailed.value.length))

const xAt = (index) => pointCount.value <= 1 ? 464 : 44 + (840 * index) / (pointCount.value - 1)
const yAt = (value) => 194 - (176 * value) / maximum.value
const buildPoints = (values) => values.map((value, index) => `${xAt(index)},${yAt(value)}`).join(' ')
const passedPoints = computed(() => buildPoints(normalizedPassed.value))
const failedPoints = computed(() => buildPoints(normalizedFailed.value))
const passedAreaPoints = computed(() => normalizedPassed.value.length > 1 ? `44,194 ${passedPoints.value} 884,194` : '')
</script>

<style scoped>
.v2-workbench-trend-chart {
  padding: var(--v2-space-3);
}

.v2-workbench-trend-chart__svg {
  display: block;
  width: 100%;
  min-height: 190px;
  overflow: visible;
}

.v2-workbench-trend-chart__grid line {
  stroke: var(--v2-border-panel);
  stroke-width: var(--v2-border-width);
  vector-effect: non-scaling-stroke;
}

.v2-workbench-trend-chart__area {
  fill: var(--v2-action-primary);
  opacity: 0.1;
}

.v2-workbench-trend-chart__line {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}

.v2-workbench-trend-chart__line--passed {
  stroke: var(--v2-action-primary);
}

.v2-workbench-trend-chart__line--failed {
  stroke: var(--v2-feedback-danger);
  stroke-dasharray: 6 6;
}

.v2-workbench-trend-chart__point {
  fill: var(--v2-surface-default);
  vector-effect: non-scaling-stroke;
  stroke-width: 2;
}

.v2-workbench-trend-chart__point--passed {
  stroke: var(--v2-action-primary);
}

.v2-workbench-trend-chart__point--failed {
  stroke: var(--v2-feedback-danger);
}

.v2-workbench-trend-chart__labels,
.v2-workbench-trend-chart__y-label {
  fill: var(--v2-text-muted);
  font-family: var(--v2-font-family-sans);
  font-size: var(--v2-font-size-tiny);
}

.v2-workbench-trend-chart__empty {
  display: grid;
  min-height: 190px;
  place-items: center;
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-body);
}

.v2-workbench-trend-chart__legend {
  display: flex;
  justify-content: flex-end;
  gap: var(--v2-space-3);
  margin-top: var(--v2-space-1);
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-caption);
}

.v2-workbench-trend-chart__legend-item {
  display: inline-flex;
  align-items: center;
  gap: var(--v2-space-micro);
}

.v2-workbench-trend-chart__legend-mark {
  width: var(--v2-space-2);
  height: 2px;
  background: var(--v2-text-muted);
}

.v2-workbench-trend-chart__legend-mark--passed {
  background: var(--v2-action-primary);
}

.v2-workbench-trend-chart__legend-mark--failed {
  background: var(--v2-feedback-danger);
}

@media (prefers-reduced-motion: reduce) {
  .v2-workbench-trend-chart__line {
    transition-duration: var(--v2-motion-reduced);
  }
}
</style>
