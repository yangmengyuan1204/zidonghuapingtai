"""网站接口自动抓取服务。

启动可见浏览器 → 自动登录前台/后台 → 遍历页面菜单 → 抓取所有 XHR/fetch 接口 → 汇总返回。

设计原则:
- 不假设页面结构,用启发式收集所有可点击菜单链接
- 每个页面等待网络空闲,捕获期间所有 XHR/fetch
- 同一接口(method+path)去重,保留首次出现的请求/响应样本
- 异常不中断整体流程,单页失败记录错误继续下一页
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

from .browser_session import _launch_chromium, _is_interesting_request

logger = logging.getLogger(__name__)

# 每页等待网络空闲的最长时间(秒)
_PAGE_TIMEOUT = 20
# 登录后等待时间(秒)
_LOGIN_WAIT = 6
# 单次抓取最多遍历页面数(防止无限爬)
_MAX_PAGES = 200
# 页面加载后等待 DOM 稳定的时间(秒)
_DOM_STABLE_WAIT = 5
# 两个页面之间的间隔(秒),避免请求过快压垮服务器
_PAGE_INTERVAL = 1
# 侧边栏菜单点击之间的间隔(秒)
_MENU_CLICK_INTERVAL = 5
# 侧边栏最多点击菜单项数
_MAX_MENU_CLICKS = 20


async def crawl_site(
    front_url: str,
    front_account: str,
    front_password: str,
    back_url: str,
    back_account: str,
    back_password: str,
) -> Dict[str, Any]:
    """抓取前后台所有页面接口。

    Returns:
    {
      "front_pages": [{"url","title","error"}],
      "back_pages": [{"url","title","error"}],
      "endpoints": [{"method","path","source":"front/back","request_body","response_status","response_sample"}],
      "stats": {"page_count","endpoint_count"}
    }
    """
    pw = await async_playwright().start()
    browser = None
    try:
        browser = await _launch_chromium(pw)
        # 前台
        front_result = await _crawl_one_site(browser, front_url, front_account, front_password, "front")
        # 后台
        back_result = await _crawl_one_site(browser, back_url, back_account, back_password, "back")
        # 合并接口(去重)
        endpoints = _merge_endpoints(front_result["endpoints"], back_result["endpoints"])
        return {
            "front_pages": front_result["pages"],
            "back_pages": back_result["pages"],
            "endpoints": endpoints,
            "stats": {
                "page_count": len(front_result["pages"]) + len(back_result["pages"]),
                "endpoint_count": len(endpoints),
            },
        }
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        await pw.stop()


async def _crawl_one_site(
    browser: Any, start_url: str, account: str, password: str, source: str
) -> Dict[str, Any]:
    """抓单个站点(前台或后台)。"""
    context = await browser.new_context()
    page = await context.new_page()
    endpoints: List[Dict[str, Any]] = []
    pages_info: List[Dict[str, Any]] = []

    # 挂载请求/响应捕获
    captured_pairs: Dict[str, Dict[str, Any]] = {}  # key=method:path → 请求+响应

    def on_request(request: Any) -> None:
        if not _is_interesting_request(request):
            return
        try:
            parsed = urlsplit(request.url)
            path = parsed.path
            method = request.method or "GET"
            key = f"{method}:{path}"
            if key not in captured_pairs:
                captured_pairs[key] = {
                    "method": method,
                    "path": path,
                    "url": request.url,
                    "source": source,
                    "query": dict(parsed.query) if parsed.query else {},
                    "headers": _filter_headers(dict(request.headers) if request.headers else {}),
                    "request_body": _safe_body(request.post_data),
                    "response_status": None,
                    "response_sample": None,
                }
        except Exception:
            return

    async def on_response(response: Any) -> None:
        try:
            request = response.request
            parsed = urlsplit(request.url)
            path = parsed.path
            method = request.method or "GET"
            key = f"{method}:{path}"
            if key not in captured_pairs:
                return
            entry = captured_pairs[key]
            if entry.get("response_status") is not None:
                return
            entry["response_status"] = response.status
            try:
                text = await asyncio.wait_for(response.text(), timeout=5)
                entry["response_sample"] = text[:500] if text else ""
            except Exception:
                entry["response_sample"] = ""
        except Exception:
            return

    page.on("request", on_request)
    page.on("response", lambda r: asyncio.ensure_future(on_response(r)))

    try:
        # 1. 打开起始页
        await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # 2. 自动登录(启发式:找账号/密码输入框+登录按钮)
        login_ok = await _try_login(page, account, password)
        await asyncio.sleep(_LOGIN_WAIT)

        # 3. 登录后展开所有菜单+滚动+收集链接
        await _expand_and_scroll(page)
        menu_links = await _collect_menu_links(page, start_url)
        pages_info.append({
            "url": page.url,
            "title": await page.title(),
            "error": None if login_ok else "登录可能失败",
        })

        # 4. 遍历每个菜单页面
        visited = {page.url}
        for link in menu_links[:_MAX_PAGES]:
            if link in visited:
                continue
            visited.add(link)
            try:
                await page.goto(link, wait_until="domcontentloaded", timeout=20000)
                await _wait_network_idle(page, _PAGE_TIMEOUT)
                await asyncio.sleep(_DOM_STABLE_WAIT)
                await _expand_and_scroll(page)
                # 不主动点查询按钮,避免触发大量列表接口压垮服务器
                await asyncio.sleep(_PAGE_INTERVAL)
                pages_info.append({
                    "url": page.url,
                    "title": await page.title(),
                    "error": None,
                })
            except Exception as exc:
                pages_info.append({
                    "url": link,
                    "title": "",
                    "error": str(exc)[:200],
                })

        endpoints = list(captured_pairs.values())
    except Exception as exc:
        pages_info.append({"url": start_url, "title": "", "error": f"站点抓取失败: {exc}"})
    finally:
        try:
            await context.close()
        except Exception:
            pass

    return {"pages": pages_info, "endpoints": endpoints}


async def _try_login(page: Any, account: str, password: str) -> bool:
    """启发式登录:找 type=text/tel 的账号框 + type=password 的密码框 + 提交按钮。

    兼容:
    - Element UI:输入框 .el-input__inner,登录按钮 .el-button--primary
    - 前端首页点击 span.routerBtn(ログイン)跳转到 /login 后再填表
    - 中英文+日文按钮文字
    """
    try:
        # 1. 先尝试找密码框(可能已在登录页)
        password_input = await page.query_selector('input[type="password"]')

        # 2. 如果没找到,尝试点击登录入口按钮跳转
        if not password_input:
            clicked = await page.evaluate("""
                () => {
                    const spans = document.querySelectorAll('span.routerBtn');
                    for (const s of spans) {
                        if ((s.textContent || '').trim() === 'ログイン') {
                            s.click();
                            return 'routerBtn';
                        }
                    }
                    const links = document.querySelectorAll('a, button, span, div');
                    for (const el of links) {
                        const text = (el.textContent || '').trim();
                        if (text === 'ログイン' || text === '登录' || text === 'Login') {
                            el.click();
                            return 'link';
                        }
                    }
                    return null;
                }
            """)
            if clicked:
                await asyncio.sleep(2)
                password_input = await page.query_selector('input[type="password"]')

        if not password_input:
            return False

        # 3. 找账号框
        account_input = await page.query_selector('.el-input__inner, input[type="text"], input[type="tel"], input[type="number"]')
        if not account_input:
            return False

        # 4. 填写表单
        await account_input.click()
        await account_input.fill("")
        await account_input.type(account, delay=30)
        await password_input.click()
        await password_input.fill("")
        await password_input.type(password, delay=30)

        # 5. 找登录按钮
        login_btn = await page.query_selector(
            'button[type="submit"], input[type="submit"], '
            'button.el-button--primary, a.el-button--primary, '
            'button:has-text("登录"), a:has-text("登录"), '
            'button:has-text("立即登录"), a:has-text("立即登录"), '
            'button:has-text("Login"), a:has-text("Login"), '
            'button:has-text("ログイン"), a:has-text("ログイン"), '
            'button:has-text("登 录"), a:has-text("登 录")'
        )
        if not login_btn:
            return False

        await login_btn.click()
        for _ in range(10):
            await asyncio.sleep(1)
            if "/login" not in page.url and "#/login" not in page.url:
                break
        return "/login" not in page.url and "#/login" not in page.url
    except Exception as exc:
        logger.warning("登录失败: %s", exc)
        return False


async def _expand_and_scroll(page: Any) -> None:
    """展开所有折叠菜单+滚动页面触发懒加载,让更多链接出现在 DOM 中。"""
    try:
        await page.evaluate("""
            () => {
                // 1. 点击所有可展开的菜单标题(常见 class)
                const selectors = [
                    '.ant-menu-submenu-title', '.el-submenu__title',
                    '.menu-title', '.nav-title', '.sidebar-title',
                    '.collapse-title', '.ant-collapse-header', '.el-collapse-item__header',
                    '[class*="menu"][class*="title"]', '[class*="sidebar"][class*="title"]'
                ];
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        try { el.click(); } catch(e) {}
                    });
                });
                // 2. 悬停在可能的菜单项上(触发 hover 展开子菜单)
                document.querySelectorAll('.menu-item, .nav-item, [class*="menu-item"]').forEach(el => {
                    try {
                        const evt = new MouseEvent('mouseenter', {bubbles: true});
                        el.dispatchEvent(evt);
                    } catch(e) {}
                });
            }
        """)
        await asyncio.sleep(1)
        # 3. 滚动页面触发懒加载
        await page.evaluate("""
            () => {
                window.scrollTo(0, document.body.scrollHeight);
                setTimeout(() => window.scrollTo(0, 0), 500);
            }
        """)
        await asyncio.sleep(1)
    except Exception:
        pass


async def _collect_menu_links(page: Any, base_url: str) -> List[str]:
    """启发式收集所有菜单链接。

    策略:
    1. 收集 <a href> 和 router-link[to]
    2. 顶部导航模式:点顶部每个菜单项→侧边栏更新→收集侧边栏菜单
    3. 纯侧边栏模式:展开所有子菜单→点击每个叶子菜单项收集跳转 URL
    """
    links: List[str] = []
    base = f"{urlsplit(base_url).scheme}://{urlsplit(base_url).netloc}"

    # 1. 收集静态链接
    try:
        static_links = await page.evaluate("""
            () => {
                const result = new Set();
                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.getAttribute('href');
                    if (href && !href.startsWith('javascript:') && !href.startsWith('mailto:')) {
                        result.add(href);
                    }
                });
                document.querySelectorAll('[to]').forEach(el => {
                    const to = el.getAttribute('to');
                    if (to) result.add(to);
                });
                return Array.from(result);
            }
        """)
    except Exception:
        static_links = []

    for link in static_links:
        if link.startswith("http"):
            if link.startswith(base):
                links.append(link)
        elif link.startswith("/"):
            links.append(f"{base}{link}")
        elif link.startswith("#/"):
            links.append(f"{base}/{link}")

    # 2. 顶部导航模式:遍历所有顶部菜单,每个菜单下收集侧边栏链接
    top_menus = await _collect_top_nav_menus(page)
    if top_menus and len(top_menus) > 1:
        for top_idx in range(len(top_menus)):
            try:
                clicked = await page.evaluate(f"""
                    () => {{
                        const tops = document.querySelectorAll('.menuContainer > div, .topbar .menu-item, header [class*="menu"] span, header [class*="menu"] div');
                        const el = tops[{top_idx}];
                        if (!el) return false;
                        el.click();
                        return true;
                    }}
                """)
                if not clicked:
                    continue
                await asyncio.sleep(2)
                await page.evaluate("""
                    () => {
                        document.querySelectorAll('.el-submenu__title').forEach(el => {
                            try { el.click(); } catch(e) {}
                        });
                    }
                """)
                await asyncio.sleep(1)
                side_links = await _collect_sidebar_links_by_click(page, base)
                for sl in side_links:
                    if sl not in links:
                        links.append(sl)
            except Exception:
                continue
    else:
        # 3. 纯侧边栏模式(无顶部导航)
        side_links = await _collect_sidebar_links_by_click(page, base)
        for sl in side_links:
            if sl not in links:
                links.append(sl)

    return links


async def _collect_top_nav_menus(page: Any) -> List[str]:
    """收集顶部导航菜单文字(用于诊断是否有顶部导航)。"""
    try:
        return await page.evaluate("""
            () => {
                const tops = document.querySelectorAll('.menuContainer > div, .topbar .menu-item, header [class*="menu"]');
                return Array.from(tops).map(el => (el.textContent || '').trim());
            }
        """)
    except Exception:
        return []


async def _click_top_menu_by_text(page: Any, keywords: List[str]) -> bool:
    """点击文字含指定关键字的顶部菜单项。返回是否点成功。"""
    try:
        for kw in keywords:
            clicked = await page.evaluate(f"""
                () => {{
                    const tops = document.querySelectorAll('.menuContainer > div, .topbar .menu-item, header [class*="menu"] span, header [class*="menu"] div');
                    for (const el of tops) {{
                        if ((el.textContent || '').trim() === '{kw}') {{
                            el.click();
                            return true;
                        }}
                    }}
                    return false;
                }}
            """)
            if clicked:
                return True
        return False
    except Exception:
        return False


async def _collect_sidebar_links_by_click(page: Any, base: str) -> List[str]:
    """点击侧边栏每个叶子菜单项,收集跳转后的 URL。"""
    links: List[str] = []
    try:
        menu_count = await page.evaluate("""
            () => document.querySelectorAll('.el-menu-item:not(.el-submenu), .ant-menu-item, li[role="menuitem"]').length
        """)
        if not menu_count:
            return links
        for i in range(min(menu_count, _MAX_MENU_CLICKS)):
            try:
                url_before = page.url
                clicked = await page.evaluate(f"""
                    () => {{
                        const items = document.querySelectorAll('.el-menu-item:not(.el-submenu), .ant-menu-item, li[role="menuitem"]');
                        const el = items[{i}];
                        if (!el) return false;
                        el.click();
                        return true;
                    }}
                """)
                if not clicked:
                    continue
                await asyncio.sleep(_MENU_CLICK_INTERVAL)
                url_after = page.url
                if url_after != url_before and url_after not in links:
                    links.append(url_after)
                # 回到原页面,保持侧边栏菜单可点
                if url_after != url_before:
                    await page.goto(url_before, wait_until="domcontentloaded", timeout=10000)
                    await asyncio.sleep(_MENU_CLICK_INTERVAL)
            except Exception:
                continue
    except Exception:
        pass
    return links


async def _wait_network_idle(page: Any, timeout: int) -> None:
    """等待网络空闲:500ms 内无新请求。"""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout * 1000)
    except Exception:
        # networkidle 超时就等 2 秒兜底
        await asyncio.sleep(2)


async def _trigger_interactions(page: Any) -> None:
    """触发常见交互以加载更多接口:点击查询/搜索按钮、展开折叠面板。"""
    try:
        await page.evaluate("""
            () => {
                // 点击查询/搜索按钮
                document.querySelectorAll('button:has-text("查询"), button:has-text("搜索"), button:has-text("确定"), .search-btn, .query-btn').forEach(b => {
                    try { b.click(); } catch(e) {}
                });
                // 展开折叠面板
                document.querySelectorAll('.collapse-header, .ant-collapse-header, .el-collapse-item__header').forEach(h => {
                    try { h.click(); } catch(e) {}
                });
            }
        """)
        await asyncio.sleep(1)
    except Exception:
        pass


def _filter_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """过滤敏感 header,只保留业务相关的。"""
    keep = {"content-type", "authorization", "admintoken", "usertoken", "token", "x-requested-with"}
    return {k: v for k, v in headers.items() if k.lower() in keep}


def _safe_body(body: Any) -> str:
    """安全处理请求体,限制长度。"""
    if not body:
        return ""
    text = body if isinstance(body, str) else str(body)
    return text[:1000]


def _merge_endpoints(*endpoint_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并多组接口,按 method:path 去重,保留首次出现。"""
    seen = set()
    merged: List[Dict[str, Any]] = []
    for ep_list in endpoint_lists:
        for ep in ep_list:
            key = f"{ep['method']}:{ep['path']}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(ep)
    return merged


__all__ = ["crawl_site"]
