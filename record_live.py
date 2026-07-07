"""实时浏览器录制脚本：跑起来就开浏览器，关掉浏览器窗口即自动保存为可执行流程。

用法：
  py -3.11 record_live.py [流程名称]
  例：py -3.11 record_live.py 样品单前台支付
      py -3.11 record_live.py 样品单后台流转到上架

流程：
1. 启动可见 Chromium 浏览器（空白页，你自己输入网址）
2. 你在里面操作样品单流程（登录→支付→后台处理等）
3. 系统实时捕获所有接口请求（终端打印）
4. 操作完直接关闭浏览器窗口（点 X）
5. 自动保存到数据库，出现在数据工厂列表
6. 之后在数据工厂页面点"执行"填参数即可回放

注意：
- 终端无法交互输入，所以流程名称用命令行参数传入，不传则用默认值+时间戳
- 保存后可在数据工厂页面改名/改描述
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ms-playwright"))

from playwright.async_api import async_playwright

from app.database import SessionLocal
from app.models import RecordedFlow, RecordedFlowStep
from app.services.har_recorder import parse_har, identify_dynamic_fields, build_flow_definition

# 静态资源后缀过滤
_STATIC_EXT = (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ico", ".ttf", ".otf", ".map")


def is_api_request(url: str, resource_type: str) -> bool:
    """判断是否为需要录制的接口请求（XHR/fetch，且非静态资源）。"""
    if resource_type not in ("xhr", "fetch"):
        return False
    lower = url.lower().split("?", 1)[0]
    if any(lower.endswith(ext) for ext in _STATIC_EXT):
        return False
    return lower.startswith(("http://", "https://"))


async def main():
    # 流程名称：命令行参数或默认值
    name = sys.argv[1].strip() if len(sys.argv) > 1 else f"录制流程_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n流程名称：{name}")
    print("正在启动浏览器（空白页），请在地址栏输入网址开始操作...")

    events = []

    async with async_playwright() as p:
        # 启动 headed 浏览器
        browser = None
        candidates = []
        env_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH") or os.environ.get("CHROME_PATH")
        if env_path:
            candidates.append(env_path)
        # 项目内置 chromium
        ms_dir = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
        if ms_dir and os.path.isdir(ms_dir):
            for d in os.listdir(ms_dir):
                if d.startswith("chromium-") and not d.startswith("chromium_headless"):
                    exe = os.path.join(ms_dir, d, "chrome-win", "chrome.exe")
                    if os.path.exists(exe):
                        candidates.append(exe)

        launch_kwargs = {"headless": False, "args": ["--no-sandbox", "--disable-gpu", "--ignore-certificate-errors"]}
        try:
            browser = await p.chromium.launch(**launch_kwargs)
        except Exception as e1:
            print(f"默认启动失败: {e1}")
            launched = False
            for exe in candidates:
                try:
                    browser = await p.chromium.launch(executable_path=exe, **launch_kwargs)
                    print(f"使用浏览器: {exe}")
                    launched = True
                    break
                except Exception as e2:
                    print(f"尝试 {exe} 失败: {e2}")
            if not launched:
                print("无法启动浏览器，请检查 chromium 安装。")
                return

        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        # 挂载 request/response 监听
        request_map = {}  # 临时存 request 信息，等 response 回来配对

        def on_request(request):
            try:
                if not is_api_request(request.url, request.resource_type):
                    return
                if request.is_navigation_request():
                    return
                body_text = request.post_data or ""
                request_map[request] = {
                    "method": request.method,
                    "url": request.url,
                    "headers": dict(request.headers),
                    "body": body_text,
                    "started_at": datetime.now().isoformat(),
                }
            except Exception as e:
                print(f"[捕获请求异常] {e}")

        async def on_response(response):
            try:
                request = response.request
                info = request_map.pop(request, None)
                if not info:
                    return
                parsed = urlparse(info["url"])
                info["path"] = parsed.path
                info["query"] = {k: v[0] for k, v in parse_qs(parsed.query).items()} if parsed.query else {}
                info["response_status"] = response.status
                try:
                    text = await response.text()
                    info["response_body"] = text
                except Exception:
                    info["response_body"] = ""
                events.append(info)
                print(f"  [{len(events)}] {info['method']} {info['path']} -> {info['response_status']}")
            except Exception as e:
                print(f"[捕获响应异常] {e}")

        page.on("request", on_request)
        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        # 打开空白页，等用户自己输入网址
        try:
            await page.goto("about:blank")
        except Exception:
            pass

        print("\n" + "=" * 60)
        print("浏览器已打开。请操作样品单流程。")
        print("操作完成后，直接关闭浏览器窗口（点右上角 X）即可保存。")
        print("=" * 60 + "\n")

        # 等待浏览器关闭：用事件_future，任一触发即结束
        done = asyncio.Future()

        def _finish(reason):
            if not done.done():
                done.set_result(reason)

        context.on("close", lambda: _finish("context closed"))
        browser.on("disconnected", lambda: _finish("browser disconnected"))
        # page 关闭（用户关标签页）也触发
        page.on("close", lambda: _finish("page closed"))

        try:
            reason = await done
            print(f"\n[触发保存] {reason}")
        except Exception as e:
            print(f"\n[等待关闭异常] {e}")

        # 兜底关闭
        try:
            await browser.close()
        except Exception:
            pass

    print(f"\n共捕获 {len(events)} 个接口请求。")
    if not events:
        print("未捕获到任何请求，不保存。")
        return

    # 转成 HAR 格式喂给 har_recorder
    har = {"log": {"entries": [
        {
            "startedDateTime": ev.get("started_at", ""),
            "request": {
                "method": ev["method"],
                "url": ev["url"],
                "headers": [{"name": k, "value": v} for k, v in ev.get("headers", {}).items()],
                "postData": {"text": ev.get("body", "")} if ev.get("body") else {},
            },
            "response": {
                "status": ev.get("response_status", 0),
                "content": {"text": ev.get("response_body", "")} if ev.get("response_body") else {},
            },
        }
        for ev in events
    ]}}

    # 复用已有解析链路
    steps = parse_har(har)
    schema = identify_dynamic_fields(steps)
    flow_def = build_flow_definition(steps, schema)

    print(f"\n识别到 {len(schema['fields'])} 个动态字段：")
    for f in schema["fields"]:
        print(f"  - {f['name']} ({f.get('label', '')})")

    # 存入数据库
    db = SessionLocal()
    try:
        flow = RecordedFlow(name=name, description=f"录制于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", base_url=flow_def.get("base_url") or None)
        db.add(flow)
        db.flush()
        for step in flow_def["steps"]:
            db_step = RecordedFlowStep(
                flow_id=flow.id,
                step_index=step["step_index"],
                method=step["method"],
                path=step["path"],
                full_url=step.get("full_url") or None,
                headers_json=step.get("headers_json"),
                body_template=step.get("body_template"),
                field_schema_json=step.get("field_schema_json"),
                response_extraction_json=step.get("response_extraction_json"),
            )
            db.add(db_step)
        db.commit()
        print(f"\n保存成功！流程 ID: {flow.id}")
        print(f"流程名称: {name}")
        print(f"步骤数: {len(flow_def['steps'])}")
        print(f'\n现在到数据工厂页面，找到这个流程点"执行"，填入参数即可回放。')
        print("如需改名/改描述，在数据工厂页面操作。")
    except Exception as e:
        db.rollback()
        print(f"保存失败: {e}")
    finally:
        db.close()

    print("\n录制结束。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已取消。")
