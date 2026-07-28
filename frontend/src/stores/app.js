/**
 * App store — 全局应用状态
 * 对齐旧应用 state.filters / _projectsCache
 * 共享 localStorage 'projectId' key
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client.js'

export const useAppStore = defineStore('app', () => {
  // 全局筛选（对齐旧应用 state.filters）
  const filters = ref({
    projectId: localStorage.getItem('projectId') || '',
    envId: '',
    recordType: '',
  })

  // 项目列表缓存（对齐旧应用 _projectsCache）
  const projectsCache = ref(null)

  function setProjectId(id) {
    filters.value.projectId = id
    if (id) localStorage.setItem('projectId', id)
    else localStorage.removeItem('projectId')
  }

  function setProjects(list) {
    projectsCache.value = list
  }

  function invalidateProjectsCache() {
    projectsCache.value = null
  }

  /**
   * 获取项目列表（带缓存）
   * 对齐旧应用 getProjects()：缓存命中直接返回，否则 fetch /api/projects
   * @returns {Promise<Array>}
   */
  async function fetchProjects() {
    if (projectsCache.value) return projectsCache.value
    const list = await api('/api/projects')
    projectsCache.value = list
    return list
  }

  return { filters, projectsCache, setProjectId, setProjects, invalidateProjectsCache, fetchProjects }
})
