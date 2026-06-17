/**
 * quick-start.js — 自动化测试平台快捷操作增强
 * 
 * 提供两种一键准备模式：
 * 1. AI准备测试包（推荐）：扫描→生成用例→生成UI步骤→预检，不自动确认
 * 2. 快捷开始（演示）：扫描→生成用例→生成UI步骤→自动确认
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
      .quick-start-bar .btn.primary {
        background: rgba(255,255,255,0.4);
        border-color: #fff;
      }
      .quick-start-bar .btn.primary:hover {
        background: rgba(255,255,255,0.6);
      }
      .quick-start-bar .status-label {
        font-size: 13px;
        opacity: 0.9;
        margin-left: auto;
      }
      .quick-start-bar .demo-badge {
        font-size: 10px;
        background: rgba(255,255,255,0.2);
        padding: 2px 8px;
        border-radius: 999px;
      }
    `;
    document.head.appendChild(style);
  }

  async function doAiPrepare() {
    const bar = document.getElementById('quickStartBar');
    const btn = document.getElementById('aiPrepareBtn');
    const statusEl = document.getElementById('quickStartStatus');
    if (!btn) return;

    const taskId = window.state?.functionalTaskId;
    if (!taskId) {
      window.showToast?.('未找到功能测试任务');
      return;
    }

    btn.disabled = true;
    if (statusEl) statusEl.textContent = '⏳ AI准备中...';

    try {
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

      const result = await window.api('/api/functional-tasks/' + taskId + '/ai-prepare', {
        method: 'POST',
        body: Object.keys(authPayload).length ? authPayload : {},
      });

      const steps = result.steps || {};
      const preflight = result.preflight || {};
      const parts = [];
      parts.push(steps.scan?.ok ? '✅扫描' : '❌扫描');
      parts.push(steps.generate_cases?.ok ? '✅用例' : '❌用例');
      parts.push(steps.generate_ui?.ok ? '✅步骤' : '❌步骤');
      if (steps.preflight && steps.preflight.ok) {
        parts.push('✅预检');
      }
      if (statusEl) statusEl.textContent = parts.join(' · ');
      if (preflight && preflight.executable_count !== undefined) {
        statusEl.textContent += ' | 可执行: ' + preflight.executable_count + '/' + preflight.total;
      }

      // 提示
      var hasFail = false;
      if (!steps.scan?.ok) hasFail = true;
      if (!steps.generate_cases?.ok) hasFail = true;
      if (steps.generate_ui && !steps.generate_ui.ok) hasFail = true;

      if (!hasFail) {
        window.showToast?.('✅ AI准备完成！请人工确认高价值用例后执行');
      } else {
        window.showToast?.('⚠️ 部分步骤失败，请手动检查');
      }

      // 刷新
      const currentView = window.state?.view;
      if (currentView === 'functionalTests') {
        if (typeof window.renderFunctionalTests === 'function') {
          await window.renderFunctionalTests();
        }
      }
    } catch (err) {
      if (statusEl) statusEl.textContent = '❌ ' + (err.message || '').slice(0, 80);
      window.showToast?.('AI准备失败：' + (err.message || '未知错误'));
    } finally {
      btn.disabled = false;
    }
  }

  async function doQuickStart() {
    const bar = document.getElementById('quickStartBar');
    const btn = document.getElementById('quickStartBtn');
    const statusEl = document.getElementById('quickStartStatus');
    if (!btn) return;

    const taskId = window.state?.functionalTaskId;
    if (!taskId) {
      window.showToast?.('未找到功能测试任务');
      return;
    }

    btn.disabled = true;
    if (statusEl) statusEl.textContent = '⏳ 演示模式执行中...';

    try {
      let authPayload = {};
      try {
        const origin = (document.querySelector('.functional-summary div:last-child strong')?.textContent || '').trim();
        const cacheKey = 'functionalScanAuth:' + origin;
        const cached = localStorage.getItem(cacheKey);
        if (cached) {
          const parsed = JSON.parse(cached);
          if (parsed && parsed.enabled) {
            authPayload = { auth: parsed, demo_mode: true };
          }
        }
      } catch (e) { /* ignore */ }

      // 显式传 demo_mode=true
      const body = Object.keys(authPayload).length ? authPayload : { demo_mode: true };

      const result = await window.api('/api/functional-tasks/' + taskId + '/quick-start', {
        method: 'POST',
        body: body,
      });

      const steps = result.steps || {};
      const parts = [];
      parts.push(steps.scan?.ok ? '✅扫描' : '❌扫描');
      parts.push(steps.generate_cases?.ok ? '✅用例' : '❌用例');
      parts.push(steps.generate_ui?.ok ? '✅步骤' : '❌步骤');
      if (statusEl) statusEl.textContent = parts.join(' · ');

      if (steps.scan?.ok && steps.generate_cases?.ok && steps.generate_ui?.ok) {
        window.showToast?.('✅ 演示模式完成！注意：AI自动确认的用例请人工复核');
      } else {
        const fails = [];
        if (!steps.scan?.ok) fails.push('扫描');
        if (!steps.generate_cases?.ok) fails.push('生成用例');
        if (!steps.generate_ui?.ok) fails.push('生成步骤');
        window.showToast?.('⚠️ 部分步骤失败：' + fails.join('、') + '，请手动处理');
      }

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

  // 修改 quick-start bar 渲染：增加 AI准备 按钮
  function patchQuickStartBar(bar) {
    if (!bar || bar.dataset.patched) return;
    bar.dataset.patched = '1';

    // 找到现有的按钮容器
    var actionsEl = bar.querySelector('.quick-start-bar-actions') || bar;
    var existingBtn = document.getElementById('quickStartBtn');

    // 在现有按钮前插入 AI准备按钮
    var aiBtn = document.createElement('button');
    aiBtn.id = 'aiPrepareBtn';
    aiBtn.className = 'btn primary';
    aiBtn.textContent = '🤖 AI准备测试包';
    aiBtn.title = '扫描→生成用例→生成UI步骤→预检，不自动确认';

    var demoBtn = existingBtn || document.createElement('button');
    if (!existingBtn) {
      demoBtn.id = 'quickStartBtn';
      demoBtn.className = 'btn';
      demoBtn.textContent = '⚡ 快捷开始(演示)';
      demoBtn.title = '扫描→生成用例→生成UI步骤→自动确认（演示用）';
    } else {
      existingBtn.textContent = '⚡ 快捷开始(演示)';
      existingBtn.title = '扫描→生成用例→生成UI步骤→自动确认（演示用）';
    }

    // 插入 AI准备按钮（在现有按钮之前）
    if (existingBtn && existingBtn.parentNode) {
      existingBtn.parentNode.insertBefore(aiBtn, existingBtn);
    } else {
      actionsEl.appendChild(aiBtn);
      actionsEl.appendChild(demoBtn);
    }

    // 在按钮后面添加演示标记
    var badge = document.createElement('span');
    badge.className = 'demo-badge';
    badge.textContent = '演示';
    if (demoBtn.nextSibling) {
      demoBtn.parentNode.insertBefore(badge, demoBtn.nextSibling);
    } else {
      demoBtn.parentNode.appendChild(badge);
    }

    // 绑定事件
    aiBtn.addEventListener('click', doAiPrepare);
    demoBtn.addEventListener('click', doQuickStart);
  }

  function tryInject() {
    // 查找功能测试详情面板
    const bar = document.getElementById('quickStartBar');
    if (bar) {
      patchQuickStartBar(bar);
      return;
    }

    // 如果没有 quickStartBar，尝试在 functional-detail 头部注入
    const detailPanel = document.querySelector('.functional-detail');
    if (!detailPanel) {
      // 重试
      setTimeout(tryInject, 500);
      return;
    }

    // 已经由 app.js 的 template 渲染了 quickStartBar，所以只需要 patch
    setTimeout(function() {
      const bar2 = document.getElementById('quickStartBar');
      if (bar2) patchQuickStartBar(bar2);
    }, 200);
  }

  // 等待 DOM 加载
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryInject);
  } else {
    tryInject();
  }

  // 每次路由切换也尝试注入
  const originalRender = window.renderFunctionalTests;
  window._originalRenderFunctionalTests = originalRender;

  window.renderFunctionalTests = async function() {
    if (originalRender) await originalRender();
    setTimeout(tryInject, 300);
  };
})();
