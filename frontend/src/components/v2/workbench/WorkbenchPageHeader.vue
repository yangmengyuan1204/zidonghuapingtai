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
  min-height: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  box-sizing: border-box;
  margin: 0 0 18px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.v2-workbench-page-header__copy {
  min-width: 0;
  flex: 1 1 auto;
}

.v2-workbench-page-header__eyebrow {
  margin: 0 0 6px;
  color: var(--v2-color-text-muted-neutral);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.v2-workbench-page-header__title {
  margin: 0;
  color: var(--v2-text-primary);
  font-size: 26px;
  font-weight: 650;
  line-height: 1.25;
  letter-spacing: -0.01em;
}

.v2-workbench-page-header__description {
  max-width: 720px;
  margin: 6px 0 0;
  color: var(--v2-text-muted);
  font-size: 13px;
  line-height: 20px;
}

.v2-workbench-page-header__actions {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 4px;
}

@media (max-width: 720px) {
  .v2-workbench-page-header {
    flex-direction: column;
    gap: 12px;
  }

  .v2-workbench-page-header__actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
