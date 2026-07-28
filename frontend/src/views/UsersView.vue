<template>
  <!-- 对齐旧应用 renderUsers()：仅 admin 可管理账号 -->
  <div class="toolbar">
    <p>仅 admin 可管理账号</p>
    <button class="btn" @click="openCreate">新增用户</button>
  </div>

  <AppTable :columns="columns" :rows="rows">
    <template #role="{ row }">
      <span class="badge" :class="badgeClass(row.role)">{{ badgeText(row.role) }}</span>
    </template>
    <template #actions="{ row }">
      <div class="actions">
        <button class="btn secondary" @click="openEdit(row)">编辑</button>
        <button class="btn danger" @click="onDelete(row)">删除</button>
      </div>
    </template>
  </AppTable>

  <AppFormDialog
    :visible="formVisible"
    :title="formTitle"
    :fields="formFields"
    :values="formValues"
    submit-label="保存"
    @close="closeForm"
    @submit="submitForm"
  />
</template>

<script setup>
/**
 * Users 视图 — 迁移自旧应用 renderUsers() + userForm()
 *
 * 对齐项：
 * - 权限：仅 admin 可访问（router 守卫 + 视图内 fetchMe 校验）
 * - API：GET/POST/PUT/DELETE /api/users
 * - 列定义：ID / 账号 / 角色(badge) / 创建时间 / 操作(编辑/删除)
 * - 表单：username / password / role(select admin/normal，默认 normal)
 * - 编辑时密码可留空（不修改密码）
 *
 * 旧应用无分页、无搜索，本视图保持一致。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { useToastStore } from '../stores/toast.js'
import AppTable from '../components/AppTable.vue'
import AppFormDialog from '../components/AppFormDialog.vue'
import { badgeText, badgeClass } from '../utils/badge.js'
import * as usersApi from '../api/modules/users.js'

const router = useRouter()
const auth = useAuthStore()
const toast = useToastStore()

const rows = ref([])
const formVisible = ref(false)
const editingItem = ref(null)
const formValues = ref({})

// 列定义（对齐旧应用 renderUsers 列）
// role / actions 用 slot，避免引入 html:true（更安全）
const columns = [
  { key: 'id', label: 'ID' },
  { key: 'username', label: '账号' },
  { key: 'role', label: '角色', slot: 'role' },
  { key: 'create_time', label: '创建时间' },
  { key: 'actions', label: '操作', slot: 'actions' },
]

const formTitle = computed(() => (editingItem.value ? '编辑用户' : '新增用户'))

// 表单字段（对齐旧应用 userForm）
// 编辑时 password 标签改为"新密码（可留空）"，且非必填
const formFields = computed(() => {
  const isEdit = !!editingItem.value
  return [
    { name: 'username', label: '账号', required: true },
    {
      name: 'password',
      label: isEdit ? '新密码（可留空）' : '密码',
      type: 'password',
      required: !isEdit,
    },
    {
      name: 'role',
      label: '角色',
      type: 'select',
      options: [
        { value: 'admin', label: 'admin' },
        { value: 'normal', label: 'normal' },
      ],
      default: 'normal',
      required: true,
    },
  ]
})

async function loadUsers() {
  try {
    rows.value = await usersApi.listUsers()
  } catch (error) {
    toast.show(error.message)
  }
}

function openCreate() {
  editingItem.value = null
  formValues.value = { role: 'normal' }
  formVisible.value = true
}

function openEdit(item) {
  editingItem.value = item
  formValues.value = { username: item.username, role: item.role, password: '' }
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
  editingItem.value = null
  formValues.value = {}
}

async function submitForm(data) {
  try {
    const payload = { ...data }
    // 对齐旧应用：编辑时密码留空表示不修改
    if (editingItem.value && !payload.password) {
      delete payload.password
    }
    if (editingItem.value) {
      await usersApi.updateUser(editingItem.value.id, payload)
    } else {
      await usersApi.createUser(payload)
    }
    toast.show('已保存')
    closeForm()
    await loadUsers()
  } catch (error) {
    toast.show(error.message)
  }
}

async function onDelete(item) {
  if (!confirm(`确定删除用户 ${item.username}？`)) return
  try {
    await usersApi.deleteUser(item.id)
    toast.show('已删除')
    await loadUsers()
  } catch (error) {
    toast.show(error.message)
  }
}

onMounted(async () => {
  // 权限校验：对齐旧应用 isAdmin() 检查
  // router 守卫已挡住未登录，此处确保 admin 角色
  if (!auth.user) {
    await auth.fetchMe()
  }
  if (!auth.isAdmin) {
    router.replace('/dashboard')
    return
  }
  await loadUsers()
})
</script>

<style scoped>
/* 使用旧应用 .toolbar / .actions / .badge 样式（来自 legacy.css） */
</style>
