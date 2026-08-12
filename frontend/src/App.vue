<template>
  <AppToast />
  <AppShell v-if="routeReady && !route.meta.public" />
  <router-view v-else-if="routeReady" />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppToast from './components/AppToast.vue'
import AppShell from './components/AppShell.vue'

const route = useRoute()
const routeReady = computed(() => route.matched.length > 0)
</script>
