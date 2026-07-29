/**
 * v2-theme-lock.js — Forest Light product theme lock
 *
 * Phase 1 only:
 * - Keep localStorage key name: "theme" (do not rename)
 * - Force product value to "forest-light"
 * - Map legacy values (shuimo/zhuanye/qingxuan/xiaolan) → forest-light
 * - Hide multi-theme switching at product layer (picker hidden via CSS)
 *
 * Does not touch API, auth, migration, or business workflows.
 */
(function () {
  'use strict';

  var KEY = 'theme';
  var PRODUCT = 'forest-light';
  var LEGACY = { shuimo: 1, zhuanye: 1, qingxuan: 1, xiaolan: 1 };

  function lock() {
    try {
      var current = localStorage.getItem(KEY) || '';
      if (current !== PRODUCT) {
        localStorage.setItem(KEY, PRODUCT);
      }
    } catch (e) { /* ignore storage errors */ }

    if (document.documentElement.dataset.theme !== PRODUCT) {
      document.documentElement.dataset.theme = PRODUCT;
    }
  }

  lock();

  // If legacy shell later writes an old theme, re-lock to Forest Light.
  try {
    var observer = new MutationObserver(function () {
      var theme = document.documentElement.dataset.theme || '';
      if (theme !== PRODUCT) {
        lock();
      }
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
  } catch (e) { /* older browsers: lock once is enough */ }

  // Expose for diagnostics only
  window.__V2_THEME__ = {
    product: PRODUCT,
    legacyMap: LEGACY,
    lock: lock,
  };
})();
