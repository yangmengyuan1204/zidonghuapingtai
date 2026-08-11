<template>
  <header class="v2-workbench-page-header">
    <div class="v2-workbench-page-header__copy">
      <p v-if="eyebrow" class="v2-workbench-page-header__eyebrow">{{ eyebrow }}</p>
      <h1 class="v2-workbench-page-header__title">{{ title }}</h1>
      <p v-if="description" class="v2-workbench-page-header__description">{{ description }}</p>
      <slot />
    </div>
    <div v-if="$slots.actions" class="v2-workbench-page-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  eyebrow: { type: String, default: '' },
})
</script>

<style scoped>
.v2-workbench-page-header {
  position: relative;
  min-height: 88px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v2-space-4);
  padding: var(--v2-space-3) var(--v2-space-4);
  border: var(--v2-border-width) solid var(--v2-page-header-border);
  border-radius: var(--v2-radius-panel);
  background: var(--v2-page-header-surface);
}

.v2-workbench-page-header::before {
  position: absolute;
  top: var(--v2-space-3);
  bottom: var(--v2-space-3);
  left: 0;
  width: calc(var(--v2-border-width) * 3);
  border-radius: 0 var(--v2-radius-xs) var(--v2-radius-xs) 0;
  background: var(--v2-page-header-accent);
  content: "";
}

.v2-workbench-page-header__copy {
  min-width: 0;
}

.v2-workbench-page-header__eyebrow {
  margin: 0 0 var(--v2-space-1);
  color: var(--v2-action-primary);
  font-size: var(--v2-font-size-caption);
  font-weight: var(--v2-font-weight-bold);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.v2-workbench-page-header__title {
  margin: 0;
  color: var(--v2-text-primary);
  font-family: var(--v2-font-family-display);
  font-size: var(--v2-font-size-heading);
  font-weight: var(--v2-font-weight-bold);
  letter-spacing: var(--v2-letter-spacing-tight);
  line-height: var(--v2-line-height-heading);
}

.v2-workbench-page-header__description {
  max-width: var(--v2-layout-description-max);
  margin: var(--v2-space-1) 0 0;
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-body);
  line-height: var(--v2-line-height-body);
}

.v2-workbench-page-header__actions {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--v2-space-1);
}

@media (max-width: 720px) {
  .v2-workbench-page-header {
    flex-direction: column;
    padding: var(--v2-space-3);
  }

  .v2-workbench-page-header__actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
