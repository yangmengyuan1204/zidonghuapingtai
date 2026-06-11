/**
 * quick-start.js — 自动化测试平台快捷操作增强
 * 
 * 在功能测试详情页顶部添加"快捷开始"按钮，实现一键扫描+生成用例+生成UI步骤。
 * 需要配合后端 /api/functional-tasks/{task_id}/quick-start 端点使用。
 */
(function () {
  'use strict';

  // 注入样式
  const STYLE_ID = 'quick-start-styles';
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .quick-start-bar {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 16px;
        margin-bottom: 16px;
        background: linear-gradient(135deg, var(--accent, #ff6b9d), var(--accent-light, #ff9ec4));
        border-radius: 10px;
        color: #fff;
      }
      .quick-start-bar .btn {
        background: rgba(255,255,255,0.25);
        border: 1px solid rgba(255,255,255,0.5);
        color: #fff;
        font-weight: 600;
        padding: 8px 20px;
        cursor: pointer;
      }
      .quick-start-bar .btn:hover {
        background: rgba(255,255,255,0.4);
      }
      .quick-start-bar .btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
      .quick-start-bar .status-label {
        font-size: 13px;
        opacity: 0.9;
        margin-left: auto;
      }
    `;
    document.head.appendChild(style);
  }

  async function doQuickStart() {
    const bar = document.getElementById('quickStartBar');
    const btn = document.getElementById('quickStartBtn');
    const statusEl = document.getElementById('quickStartStatus');
    if (!btn) return;

    // 从 state 获取 taskId
    const taskId = window.state?.functionalTaskId;
    if (!taskId) {
      window.showToast?.('未找到功能测试任务');
      return;
    }

    btn.disabled = true;
    if (statusEl) statusEl.textContent = '⏳ 执行中...';

    try {
      // 读取登录配置
      let authPayload = {};
      try {
        const origin = (document.querySelector('.functional-summary div:last-child strong')?.textContent || '').trim();
        const cacheKey = 'functionalScanAuth:' + origin;
        const cached = localStorage.getItem(cacheKey);
        if (cached) {
          const parsed = JSON.parse(cached);
          if (parsed && parsed.enabled) {
            authPayload = { auth: parsed };
          }
        }
      } catch (e) { /* ignore */ }

      const result = await window.api('/api/functional-tasks/' + taskId + '/quick-start', {
        method: 'POST',
        body: Object.keys(authPayload).length ? authPayload : {},
      });

      const steps = result.steps || {};
      const parts = [];
      parts.push(steps.scan?.ok ? '✅扫描' : '❌扫描');
      parts.push(steps.generate_cases?.ok ? '✅用例' : '❌用例');
      parts.push(steps.generate_ui?.ok ? '✅步骤' : '❌步骤');
      if (statusEl) statusEl.textContent = parts.join(' · ');

      // 提示
      if (steps.scan?.ok && steps.generate_cases?.ok && steps.generate_ui?.ok) {
        window.showToast?.('✅ 快捷开始完成！所有用例已自动生成并确认');
      } else {
        const fails = [];
        if (!steps.scan?.ok) fails.push('扫描');
        if (!steps.generate_cases?.ok) fails.push('生成用例');
        if (!steps.generate_ui?.ok) fails.push('生成步骤');
        window.showToast?.('⚠️ 部分步骤失败：' + fails.join('、') + '，请手动处理');
      }

      // 刷新当前视图
      const currentView = window.state?.view;
      if (currentView === 'functionalTests') {
        if (typeof window.renderFunctionalTests === 'function') {
          await window.renderFunctionalTests();
        }
      }
    } catch (err) {
      if (statusEl) statusEl.textContent = '❌ ' + (err.message || '').slice(0, 80);
      window.showToast?.('快捷开始失败：' + (err.message || '未知错误'));
    } finally {
      btn.disabled = false;
    }
  }

  function tryInject() {
    // 查找功能测试详情面板
    const detailPanel = document.querySelector('section.panel.functional-detail');
    if (!detailPanel) return false;
    // 已注入则跳过
    if (document.getElementById('quickStartBar')) return true;

    // 获取 task 标题
    const taskId = window.state?.functionalTaskId;
    if (!taskId) return false;

    // 创建快捷开始栏，插入到 panel-title 之前
    const bar = document.createElement('div');
    bar.className = 'quick-start-bar';
    bar.id = 'quickStartBar';
    bar.innerHTML = `
      <strong>⚡ 快捷开始</strong>
      <span style="font-size:13px;opacity:0.9">扫描→生成用例→生成步骤→自动确认</span>
      <button class="btn" id="quickStartBtn">🚀 一键执行</button>
      <span class="status-label" id="quickStartStatus">就绪</span>
    `;

    // 插入到 panel-title 之前（作为第一个子元素）
    const panelTitle = detailPanel.querySelector('.panel-title');
    if (panelTitle) {
      detailPanel.insertBefore(bar, panelTitle);
    } else {
      // 兜底：插入到 detailPanel 最前面
      detailPanel.insertBefore(bar, detailPanel.firstChild);
    }

    document.getElementById('quickStartBtn')?.addEventListener('click', doQuickStart);
    return true;
  }

  // 等待 app 加载完成后启动
  function init() {
    if (window.state && window.api) {
      tryInject();
      // 监听 DOM 变化（视图切换后重新注入）
      const appEl = document.querySelector('#app');
      if (appEl) {
        const observer = new MutationObserver(() => {
          if (!document.getElementById('quickStartBar')) {
            tryInject();
          }
        });
        observer.observe(appEl, { childList: true, subtree: true });
      }
    } else {
      setTimeout(init, 500);
    }
  }

  // 启动
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
