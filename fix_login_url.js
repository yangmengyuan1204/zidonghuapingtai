const fs = require('fs');
let c = fs.readFileSync('static/app.js', 'utf8');

// 找到 inferLoginUrl 函数
const idx = c.indexOf('function inferLoginUrl');
let end = c.indexOf('\nfunction ', idx + 10);
if (end < 0) end = c.indexOf('\n  function ', idx + 10);
if (end < 0) end = c.length;
const oldFunc = c.substring(idx, Math.min(end, idx + 500));

console.log('=== OLD inferLoginUrl ===');
console.log(oldFunc.substring(0, 200));

// 新函数：支持 SPA hash 路由
const newFunc = [
  'function inferLoginUrl(targetUrl) {',
  '  try {',
  '    const url = new URL(targetUrl);',
  '    // 检测 SPA hash 路由（如 /#/xxx 或 /#!/xxx）',
  '    if (url.hash && url.hash.includes("/")) {',
  '      const base = url.origin + url.pathname;',
  '      const hashPrefix = url.hash.startsWith("#!") ? "#!" : "#";',
  '      return base + hashPrefix + "/login";',
  '    }',
  '    if (url.pathname.toLowerCase().includes("login")) return url.toString();',
  '    return url.origin + "/login";',
  '  } catch {',
  '    return "";',
  '  }',
  '}',
].join('  '); // single line style to match file

// Actually, write as single line like the existing code
const newFuncLine = 'function inferLoginUrl(targetUrl) {  try {    const url = new URL(targetUrl);    if (url.hash && url.hash.includes("/")) {      const base = url.origin + url.pathname;      const hashPrefix = url.hash.startsWith("#!") ? "#!" : "#";      return base + hashPrefix + "/login";    }    if (url.pathname.toLowerCase().includes("login")) return url.toString();    return url.origin + "/login";  } catch {    return "";  }}';

c = c.replace(oldFunc, newFuncLine);

if (c.includes('url.hash && url.hash.includes("/")')) {
  console.log('✓ Frontend fix applied');
} else {
  console.log('✗ Frontend fix NOT applied');
}

fs.writeFileSync('static/app.js', c, 'utf8');
console.log('File written');
