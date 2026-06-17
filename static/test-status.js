/**
 * test-status.js — 测试用例状态标记 + 统计看板
 * 
 * 为功能测试详情页自动注入：
 * 1. 每个用例行上的可点击状态指示器
 * 2. 顶部统计卡片（总计/通过/失败/阻塞/跳过）
 * 3. 批量状态标记栏
 * 4. 结果筛选
 */
(function () {
  'use strict';

  const STYLE_ID = 'test-status-styles';
  const STATUSES = ['untested', 'passed', 'failed', 'blocked', 'skipped'];
  const STATUS_LABELS = { untested: '未执行', passed: '通过', failed: '失败', blocked: '阻塞', skipped: '跳过' };
  const STATUS_COLORS = { untested: '#9ca3af', passed: '#34d399', failed: '#f87171', blocked: '#fbbf24', skipped: '#d1d5db' };

  let _taskId = '';
  let _filter = '';
  let _selected = new Set();
  let _refreshFn = null;

  // ─── 注入样式 ─────────────────────────────────────

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = `
.test-stats{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:16px}
.test-stat-card{padding:16px 14px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--surface);backdrop-filter:blur(12px);text-align:center;cursor:pointer;transition:all 0.25s ease;position:relative;overflow:hidden}
.test-stat-card:hover{transform:translateY(-3px);box-shadow:0 6px 20px rgba(0,0,0,0.08)}
.test-stat-card.active{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-glow)}
.test-stat-card .stat-num{display:block;font-size:26px;font-weight:700;line-height:1.2}
.test-stat-card .stat-label{display:block;margin-top:4px;font-size:12px;color:var(--muted);font-weight:600;letter-spacing:0.04em}
.test-stat-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:middle}
.sr-picker{display:inline-flex;gap:3px;align-items:center;padding:3px 6px;border-radius:20px;background:rgba(0,0,0,0.04);transition:all 0.2s ease;white-space:nowrap}
.sr-picker:hover{background:rgba(0,0,0,0.08)}
.sr-dot{width:16px;height:16px;border-radius:50%;border:2px solid transparent;cursor:pointer;transition:all 0.2s ease;display:inline-block}
.sr-dot:hover{transform:scale(1.3)}
.sr-dot.active{border-color:var(--text);box-shadow:0 0 0 2px rgba(255,255,255,0.8);transform:scale(1.15)}
.sr-label{display:none;margin-left:4px;font-size:11px;font-weight:600;color:var(--muted);vertical-align:middle}
.sr-picker:hover .sr-label{display:inline}
.batch-bar{display:flex;align-items:center;gap:10px;padding:8px 14px;margin-bottom:12px;background:rgba(255,255,255,0.5);border:1px dashed var(--line);border-radius:var(--radius-sm);min-height:42px;flex-wrap:wrap}
.batch-bar .bc{font-size:13px;font-weight:600;color:var(--muted);margin-right:auto}
.batch-bar .bd{display:inline-flex;gap:3px;align-items:center}
.batch-bar .bd .sr-dot{width:20px;height:20px}
.case-cb{width:18px;height:18px;accent-color:var(--accent);cursor:pointer;margin:0;vertical-align:middle}
.case-cb-all{width:18px;height:18px;accent-color:var(--accent);cursor:pointer;margin:0;vertical-align:middle}
    `;
    document.head.appendChild(s);
  }

  // ─── 渲染函数 ─────────────────────────────────────

  function statsHTML(stats) {
    const items = [
      { k:'total', l:'总计', c:'#8b5cf6', n:stats.total },
      { k:'untested', l:'未执行', c:STATUS_COLORS.untested, n:stats.untested },
      { k:'passed', l:'通过', c:STATUS_COLORS.passed, n:stats.passed },
      { k:'failed', l:'失败', c:STATUS_COLORS.failed, n:stats.failed },
      { k:'blocked', l:'阻塞', c:STATUS_COLORS.blocked, n:stats.blocked },
    ];
    if (stats.skipped > 0) items.push({ k:'skipped', l:'跳过', c:STATUS_COLORS.skipped, n:stats.skipped });
    return items.map(i => {
      const active = _filter === i.k || (!_filter && i.k === 'total');
      return `<div class="test-stat-card ${active?'active':''}" data-sk="${i.k}">
        <span class="stat-num" style="color:${i.c}">${i.k!=='total' ? `<span class="test-stat-dot" style="background:${i.c}"></span>` : ''}${i.n}</span>
        <span class="stat-label">${i.l}</span>
      </div>`;
    }).join('');
  }

  function pickerHTML(caseId, current) {
    return STATUSES.map(s => {
      const active = s === (current || 'untested');
      return `<span class="sr-dot ${active?'active':''}" data-cid="${caseId}" data-st="${s}" style="background:${STATUS_COLORS[s]}" title="${STATUS_LABELS[s]}"></span>`;
    }).join('');
  }

  function batchBarHTML() {
    const dots = STATUSES.map(s => 
      `<span class="sr-dot" data-st="${s}" style="background:${STATUS_COLORS[s]}" title="标记为「${STATUS_LABELS[s]}」"></span>`
    ).join('');
    return `<div class="batch-bar" id="bbar" style="display:none">
      <span class="bc" id="bcnt">已选 0 个</span>
      <span style="font-size:12px;color:var(--muted)">批量标记:</span>
      <span class="bd">${dots}</span>
      <button class="btn secondary" id="bclear" style="min-height:30px;padding:0 12px;font-size:12px" type="button">取消</button>
    </div>`;
  }

  // ─── API 调用 ─────────────────────────────────────

  async function putStatus(caseId, v) {
    try { await window.api(`/api/functional-cases/${caseId}/status`, { method:'PUT', body:{ test_result:v } }); return true; }
    catch { return false; }
  }
  async function batchStatus(taskId, ids, v) {
    try {
      await window.api(`/api/functional-tasks/${taskId}/cases/batch-status`, { method:'POST', body:{ case_ids:ids, test_result:v } });
      window.showToast?.(`已标记 ${ids.length} 个用例为「${STATUS_LABELS[v]}」`);
      return true;
    } catch { return false; }
  }
  async function getStats(taskId) {
    try { return await window.api(`/api/functional-tasks/${taskId}/cases/stats`); }
    catch { return null; }
  }

  // ─── DOM 注入 + 事件绑定 ────────────────────────

  function inject() {
    const detail = document.querySelector('.functional-detail.panel');
    if (!detail) return false;

    // 从 state 获取 taskId
    _taskId = window.state?.functionalTaskId || '';
    if (!_taskId) return false;

    // 已经注入过了
    if (document.getElementById('ts-stats-wrap')) return true;

    // 1. 注入统计看板（在 panel-title 后面）
    const title = detail.querySelector('.panel-title');
    if (title) {
      const wrap = document.createElement('div');
      wrap.id = 'ts-stats-wrap';
      wrap.style.cssText = 'padding:12px 20px 0';
      title.after(wrap);
      getStats(_taskId).then(stats => {
        if (stats) wrap.innerHTML = `<div class="test-stats">${statsHTML(stats)}</div>`;
      });
    }

    // 2. 注入批量操作栏（在 table-wrap 前面）
    const tableWrap = detail.querySelector('.table-wrap');
    if (tableWrap) {
      const batchWrap = document.createElement('div');
      batchWrap.id = 'ts-batch-wrap';
      batchWrap.innerHTML = batchBarHTML();
      tableWrap.parentNode.insertBefore(batchWrap, tableWrap);
    }

    // 3. 给表格添加 checkbox 列 + 状态选择器
    enhanceTable();

    // 4. 绑定事件
    bindEvents();

    // 暴露刷新统计方法
    window.TestStatusModule._refreshStats = () => {
      getStats(_taskId).then(stats => {
        const el = document.querySelector('#ts-stats-wrap .test-stats');
        if (el && stats) el.innerHTML = statsHTML(stats);
      });
    };

    return true;
  }

  function enhanceTable() {
    const table = document.querySelector('.functional-detail table');
    if (!table) return;

    // 添加表头
    const thead = table.querySelector('thead tr');
    if (thead) {
      // 添加 checkbox 表头
      const thCb = document.createElement('th');
      thCb.style.cssText = 'width:36px;text-align:center';
      thCb.innerHTML = '<input type="checkbox" class="case-cb-all" id="selAll">';
      thead.insertBefore(thCb, thead.firstChild);

      // 添加状态表头
      const thSt = document.createElement('th');
      thSt.textContent = '结果';
      thSt.style.cssText = 'width:100px';
      // 放在第二列（checkbox 后面）
      const refNode = thead.children[1]; // 原来的第一列
      thead.insertBefore(thSt, refNode);
    }

    // 处理每一行
    const rows = table.querySelectorAll('tbody tr');
    rows.forEach(row => {
      const caseId = extractCaseId(row);
      if (!caseId) {
        console.warn('无法提取用例ID，该行已跳过批量操作:', row.innerHTML.slice(0, 100));
        return;
      }

      // checkbox
      const tdCb = document.createElement('td');
      tdCb.style.cssText = 'text-align:center;vertical-align:middle';
      tdCb.innerHTML = `<input type="checkbox" class="case-cb" value="${caseId}">`;
      row.insertBefore(tdCb, row.firstChild);

      // 状态选择器
      const current = row.dataset.testResult || 'untested';
      const tdSt = document.createElement('td');
      tdSt.style.cssText = 'white-space:nowrap;vertical-align:middle';
      tdSt.innerHTML = `<span class="sr-picker">${pickerHTML(caseId, current)}</span>`;
      const ref = row.children[1]; // 原来的第一列
      row.insertBefore(tdSt, ref);
    });
  }

  function extractCaseId(row) {
    // 尝试方法1：从行 HTML 中匹配 API 路径 /api/functional-cases/{id}
    const html = row.innerHTML;
    let m = html.match(/\/api\/functional-cases\/(\d+)/i);
    if (m) return Number(m[1]);
    // 尝试方法2：匹配 generate-ui-steps/\d+ 或类似 pattern
    m = html.match(/generate-ui-steps[\/\\](\d+)/i);
    if (m) return Number(m[1]);
    // 尝试方法3：匹配 onclick 中的数字
    m = html.match(/onclick[^>]*?(\d+)/i);
    if (m) return Number(m[1]);
    // 尝试方法4：查找 data-case-id 属性
    const attrEl = row.querySelector('[data-case-id]');
    if (attrEl) return Number(attrEl.dataset.caseId);
    // 尝试方法5：从第一个按钮的 href / data 提取
    const btn = row.querySelector('.btn');
    if (btn) {
      m = (btn.getAttribute('onclick') || btn.getAttribute('href') || '').match(/(\d+)/);
      if (m) return Number(m[1]);
    }
    return null;
  }

  function bindEvents() {
    const detail = document.querySelector('.functional-detail');
    if (!detail) return;

    // 状态点点击
    detail.addEventListener('click', async (e) => {
      const dot = e.target.closest('.sr-dot');
      if (!dot) return;

      // 批量操作栏的点
      if (dot.closest('.bd')) {
        const st = dot.dataset.st;
        if (_selected.size === 0) { window.showToast?.('请先勾选用例'); return; }
        if (await batchStatus(_taskId, [..._selected], st)) {
          _selected.clear(); _refresh(); updateBatchBar();
        }
        return;
      }

      const cid = Number(dot.dataset.cid);
      const st = dot.dataset.st;
      if (!cid || !st) return;

      // UI 乐观更新
      const picker = dot.closest('.sr-picker');
      if (picker) {
        picker.querySelectorAll('.sr-dot').forEach(d => d.classList.remove('active'));
        dot.classList.add('active');
      }

      // 保存状态到行 data 属性
      const row = dot.closest('tr');
      if (row) row.dataset.testResult = st;

      if (await putStatus(cid, st)) {
        window.TestStatusModule._refreshStats?.();
      }
    });

    // 统计卡点击（筛选）
    detail.addEventListener('click', (e) => {
      const card = e.target.closest('.test-stat-card');
      if (!card) return;
      const k = card.dataset.sk;
      _filter = k === 'total' ? '' : k;
      document.querySelectorAll('.test-stat-card').forEach(c => c.classList.toggle('active', c.dataset.sk === k));
      _refresh();
    });

    // 单选框
    detail.addEventListener('change', (e) => {
      const cb = e.target.closest('.case-cb');
      if (!cb || cb.id === 'selAll') return;
      const id = Number(cb.value);
      if (cb.checked) _selected.add(id);
      else _selected.delete(id);
      updateBatchBar();
    });

    // 全选
    const selAll = document.getElementById('selAll');
    if (selAll) {
      selAll.addEventListener('change', () => {
        const checked = selAll.checked;
        document.querySelectorAll('.case-cb').forEach(cb => {
          if (cb.id === 'selAll') return;
          cb.checked = checked;
          const id = Number(cb.value);
          if (checked) _selected.add(id);
          else _selected.delete(id);
        });
        updateBatchBar();
      });
    }

    // 取消选择
    const bclear = document.getElementById('bclear');
    if (bclear) {
      bclear.addEventListener('click', () => {
        _selected.clear();
        document.querySelectorAll('.case-cb').forEach(cb => cb.checked = false);
        if (selAll) selAll.checked = false;
        updateBatchBar();
      });
    }
  }

  function updateBatchBar() {
    const bar = document.getElementById('bbar');
    const cnt = document.getElementById('bcnt');
    if (bar) bar.style.display = _selected.size > 0 ? 'flex' : 'none';
    if (cnt) cnt.textContent = `已选 ${_selected.size} 个用例`;
  }

  function _refresh() {
    if (typeof _refreshFn === 'function') _refreshFn();
    else if (typeof window.renderFunctionalTests === 'function') window.renderFunctionalTests();
  }

  // ─── 外部接口 ─────────────────────────────────────

  window.TestStatusModule = {
    getFilter() { return _filter; },
    clearSelection() { _selected.clear(); updateBatchBar(); },
    _refreshStats: null,
  };

  // ─── 自动初始化 ────────────────────────────────────

  function tryInject() {
    if (!window.state || !window.api) { setTimeout(tryInject, 500); return; }
    if (inject() || document.querySelector('.functional-detail')) return;
    // 还没渲染，等 DOM 变化
  }

  injectStyles();
  tryInject();

  // 监听 DOM 变化
  const obs = new MutationObserver(() => {
    if (!document.getElementById('ts-stats-wrap') && document.querySelector('.functional-detail.panel')) {
      inject();
    }
  });
  obs.observe(document.querySelector('#app') || document.body, { childList: true, subtree: true });

  // 暴露给 quick-start.js 使用
  if (!window._testStatusInit) {
    window._testStatusInit = tryInject;
    window._testStatusRefresh = () => window.TestStatusModule._refreshStats?.();
  }

})();
