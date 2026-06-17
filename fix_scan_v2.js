const fs = require('fs');

// ====== 修复 1: functional_testing.py ======
let c = fs.readFileSync('app/functional_testing.py', 'utf8');

// 1.1 验证 skip-nav 修复是否存在
if (!c.includes('跳过重复导航（支持 SPA hash 路由）')) {
  // 修复 _login_before_scan: 跳转到登录页前检查是否已经在登录页
  const oldNav = `    _scan_trace(trace, f"打开登录页：{login_url}")
    page.goto(login_url, wait_until="domcontentloaded")
    page.wait_for_timeout(500)`;
  const newNav = `    # 如果当前页面已经是登录页，跳过重复导航（支持 SPA hash 路由）
    if not _looks_like_login_page(page, expected_url=login_url):
      _scan_trace(trace, f"打开登录页：{login_url}")
      page.goto(login_url, wait_until="domcontentloaded")
      page.wait_for_timeout(500)
    else:
      _scan_trace(trace, f"当前页面已是登录页，跳过导航：{page.url}")`;
  if (c.includes(oldNav)) {
    c = c.replace(oldNav, newNav);
    console.log('✓ skip-nav fix applied');
  } else {
    console.log('✗ skip-nav fix NOT applied (old text not found)');
    // Try without f-string
    const oldNav2 = '    _scan_trace(trace, f"打开登录页：{login_url}")';
    if (c.includes(oldNav2)) {
      console.log('  but f-string pattern exists');
    }
  }
} else {
  console.log('✓ skip-nav fix already exists');
}

// 1.2 修复 login submit 的定位器 — 添加更多 UI 框架
// 在 _login_before_scan 中找到 submit_locators 定义并追加更多定位器
const oldSubmitLocators = `    submit_locators = _locator_candidates(
        auth.get("submit_locator"),
        [
            'button[type="submit"]',
            'input[type="submit"]',
            "text=登录",
            "text=登入",
            "text=登陆",
            "text=Login",
            "text=Sign in",
            "text=ログイン",
        ],
    )`;

const newSubmitLocators = `    submit_locators = _locator_candidates(
        auth.get("submit_locator"),
        [
            'button[type="submit"]',
            'button[class*="btn-primary"]',
            'button[class*="el-button--primary"]',
            '.el-button--primary',
            '.ant-btn-primary',
            'input[type="submit"]',
            'button:has-text("登录")',
            'button:has-text("登入")',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button:has-text("ログイン")',
            'a:has-text("登录")',
            'a:has-text("Login")',
            'text=登录',
            "text=登入",
            "text=登陆",
            "text=Login",
            "text=Sign in",
            "text=ログイン",
        ],
    )`;

if (c.includes(oldSubmitLocators)) {
  c = c.replace(oldSubmitLocators, newSubmitLocators);
  console.log('✓ submit locators expanded');
} else {
  console.log('✗ submit locators NOT replaced');
}

// 1.3 添加 --ignore-certificate-errors 到 launch args
if (c.includes('"--disable-setuid-sandbox"')) {
  // Check if already has ignore-certificate-errors
  if (!c.includes('ignore-certificate-errors')) {
    c = c.replace(
      '        "--disable-setuid-sandbox",',
      '        "--disable-setuid-sandbox",\n        "--ignore-certificate-errors",'
    );
    console.log('✓ ignore-certificate-errors flag added');
  } else {
    console.log('✓ ignore-certificate-errors already exists');
  }
}

fs.writeFileSync('app/functional_testing.py', c, 'utf8');
console.log('✓ functional_testing.py written');

// ====== 修复 2: static/app.js ======
let j = fs.readFileSync('static/app.js', 'utf8');

// 2.1 验证 inferLoginUrl 修复
if (j.includes('url.hash && url.hash.includes("/")')) {
  console.log('✓ inferLoginUrl SPA fix already exists');
} else {
  const oldInfer = j.indexOf('function inferLoginUrl');
  const saveStart = j.indexOf('function saveFunctionalScanAuth');
  if (oldInfer > 0 && saveStart > oldInfer) {
    // Need to also check if inferLoginUrl is followed by loadFunctionalScanAuth
    // If loadFunctionalScanAuth was deleted, we need to restore it
    const loadStart = j.indexOf('function loadFunctionalScanAuth');
    const between = j.substring(oldInfer, saveStart);
    const newInferFunc = 'function inferLoginUrl(targetUrl) {  try {    const url = new URL(targetUrl);    if (url.hash && url.hash.includes("/")) {      const base = url.origin + url.pathname;      const hashPrefix = url.hash.startsWith("#!") ? "#!" : "#";      return base + hashPrefix + "/login";    }    if (url.pathname.toLowerCase().includes("login")) return url.toString();    return url.origin + "/login";  } catch {    return "";  }}';
    
    if (loadStart < 0) {
      // loadFunctionalScanAuth is missing, restore from git
      const orig = fs.readFileSync('git_original.js', 'utf8');
      const loadFunc = orig.substring(
        orig.indexOf('function loadFunctionalScanAuth'),
        orig.indexOf('function saveFunctionalScanAuth')
      );
      j = j.substring(0, oldInfer) + newInferFunc + loadFunc + j.substring(saveStart);
      console.log('✓ restored loadFunctionalScanAuth and updated inferLoginUrl');
    } else {
      j = j.substring(0, oldInfer) + newInferFunc + j.substring(loadStart);
      console.log('✓ inferLoginUrl updated');
    }
  }
}

fs.writeFileSync('static/app.js', j, 'utf8');
console.log('✓ app.js written');

// ====== 语法验证 ======
try {
  new (require('vm').Script)(j);
  console.log('✓ app.js syntax OK');
} catch(e) {
  console.log('✗ app.js syntax ERROR:', e.message.substring(0, 300));
}
