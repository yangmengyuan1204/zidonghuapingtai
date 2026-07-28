/**
 * migration-bridge.js — Vue3 迁移桥接脚本
 *
 * 职责：在旧应用中拦截已迁移页面的导航，重定向到 Vue3 应用 (/v3/)。
 * 安全保证：migration-config.json 的 migrated 为空数组时，零拦截、零影响。
 *
 * 原理：
 * 1. 异步 fetch /static/migration-config.json 获取已迁移页面列表
 * 2. 在 document capture 阶段拦截 [data-view] 点击事件
 * 3. 若目标 view 在 migrated 列表内，阻止旧应用的事件处理，跳转 /v3/<view>
 * 4. capture 阶段先于旧应用 bubble 阶段执行，确保旧应用不会渲染已迁移页面
 */
(function () {
  'use strict';

  var CONFIG_URL = '/static/migration-config.json';
  var V3_BASE = '/v3/';

  function activateInitialHash(retriesLeft) {
    var match = String(window.location.hash || '').match(/^#\/([A-Za-z][A-Za-z0-9_-]*)$/);
    if (!match || !migratedSet) return;

    var view = match[1];
    if (migratedSet.has(view)) {
      window.location.href = V3_BASE + view;
      return;
    }

    var button = document.querySelector('[data-view="' + view + '"]');
    if (button) {
      button.click();
      return;
    }
    if (retriesLeft > 0) {
      setTimeout(function () { activateInitialHash(retriesLeft - 1); }, 50);
    }
  }
  var migratedSet = null; // null=未加载, Set=已加载

  // 异步加载迁移配置
  fetch(CONFIG_URL)
    .then(function (res) { return res.json(); })
    .then(function (config) {
      migratedSet = new Set(config.migrated || []);
      activateInitialHash(20);
    })
    .catch(function () {
      migratedSet = new Set();
      activateInitialHash(20);
      // 加载失败，设为空集合，不重定向任何页面
      migratedSet = new Set();
    });

  // capture 阶段拦截导航点击
  document.addEventListener('click', function (e) {
    // 配置未加载或空集合时不拦截
    if (!migratedSet || migratedSet.size === 0) return;

    // 查找最近的 [data-view] 祖先
    var target = e.target.closest ? e.target.closest('[data-view]') : null;
    if (!target) return;

    var view = target.getAttribute('data-view');
    if (!view) return;

    // 目标页面已迁移，阻止旧应用处理，跳转 Vue3
    if (migratedSet.has(view)) {
      e.preventDefault();
      e.stopPropagation();
      window.location.href = V3_BASE + view;
    }
  }, true); // true = capture 阶段
})();
