<template>
  <component :is="tag" class="v2-workbench-panel" :aria-label="ariaLabel || undefined">
    <header v-if="title || subtitle || $slots.actions" class="v2-workbench-panel__header">
      <div class="v2-workbench-panel__heading">
        <h2 v-if="title" class="v2-workbench-panel__title">{{ title }}</h2>
        <p v-if="subtitle" class="v2-workbench-panel__subtitle">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="v2-workbench-panel__actions">
        <slot name="actions" />
      </div>
    </header>
    <div class="v2-workbench-panel__body">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="v2-workbench-panel__footer">
      <slot name="footer" />
    </footer>
  </component>
</template>

<script setup>
defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  tag: { type: String, default: 'section' },
  ariaLabel: { type: String, default: '' },
})
</script>

<style scoped>
.v2-workbench-panel {
  overflow: hidden;
  border: var(--v2-border-width) solid var(--v2-border-panel);
  border-radius: var(--v2-radius-panel);
  background: var(--v2-panel-surface);
  box-shadow: var(--v2-shadow-panel);
}

.v2-workbench-panel__header {
  display: flex;
  min-height: 52px;
  align-items: center;
  justify-content: space-between;
  gap: var(--v2-space-3);
  padding: var(--v2-space-2) var(--v2-space-3);
  border-bottom: var(--v2-border-width) solid var(--v2-panel-header-border);
  background: var(--v2-panel-header-surface);
}

.v2-workbench-panel__heading {
  min-width: 0;
}

.v2-workbench-panel__title {
  margin: 0;
  color: var(--v2-text-primary);
  font-size: var(--v2-panel-title-font-size);
  font-weight: var(--v2-font-weight-semibold);
}

.v2-workbench-panel__subtitle {
  margin: var(--v2-space-micro) 0 0;
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-caption);
}

.v2-workbench-panel__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: var(--v2-space-1);
}

.v2-workbench-panel__body {
  min-width: 0;
}

.v2-workbench-panel__footer {
  padding: var(--v2-space-2) var(--v2-space-3);
  border-top: var(--v2-border-width) solid var(--v2-border-panel);
  background: var(--v2-panel-footer-surface);
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-caption);
}
</style>
