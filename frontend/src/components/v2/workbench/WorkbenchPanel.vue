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
  display: grid;
  gap: 10px;
  min-width: 0;
  overflow: visible;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.v2-workbench-panel__header {
  display: flex;
  min-height: 0;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 2px;
  border: 0;
  background: transparent;
}

.v2-workbench-panel__heading {
  display: flex;
  flex: 1 1 auto;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.v2-workbench-panel__title {
  margin: 0;
  color: var(--v2-text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.v2-workbench-panel__subtitle {
  margin: 0;
  color: var(--v2-text-muted);
  font-size: 12px;
  text-align: right;
}

.v2-workbench-panel__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
}

@media (max-width: 720px) {
  .v2-workbench-panel__heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }

  .v2-workbench-panel__subtitle {
    text-align: left;
  }
}

.v2-workbench-panel__body {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--v2-color-card-border-subtle);
  border-radius: var(--v2-radius-panel);
  background: var(--v2-surface-default);
  box-shadow: var(--v2-shadow-card-enterprise);
}

.v2-workbench-panel__footer {
  padding: 10px 16px;
  border: 1px solid var(--v2-color-card-border-subtle);
  border-radius: var(--v2-radius-panel);
  background: var(--v2-surface-default);
  color: var(--v2-text-muted);
  font-size: 12px;
  box-shadow: var(--v2-shadow-card-enterprise);
}
</style>
