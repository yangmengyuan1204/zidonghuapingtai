<template>
  <AppToast />
  <AppShell v-if="!route.meta.public" />
  <router-view v-else />
</template>

<script setup>
import { useRoute } from 'vue-router'
import AppToast from './components/AppToast.vue'
import AppShell from './components/AppShell.vue'

const route = useRoute()
</script>
