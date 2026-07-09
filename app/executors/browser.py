import os
import shutil
from pathlib import Path
from typing import Any


def _browser_executable_candidates() -> list[str]:
    candidates = [
        os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"),
        os.getenv("CHROME_PATH"),
        os.getenv("EDGE_PATH"),
    ]
    for env_name, relative in [
        ("ProgramFiles", r"Google\Chrome\Application\chrome.exe"),
        ("ProgramFiles(x86)", r"Google\Chrome\Application\chrome.exe"),
        ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe"),
        ("ProgramFiles", r"Microsoft\Edge\Application\msedge.exe"),
        ("ProgramFiles(x86)", r"Microsoft\Edge\Application\msedge.exe"),
        ("LOCALAPPDATA", r"Microsoft\Edge\Application\msedge.exe"),
        ("LOCALAPPDATA", r"Chromium\Application\chrome.exe"),
        ("LOCALAPPDATA", r"Google\Chrome Beta\Application\chrome.exe"),
        ("LOCALAPPDATA", r"Google\Chrome SxS\Application\chrome.exe"),
    ]:
        root = os.getenv(env_name)
        if root:
            candidates.append(str(Path(root) / relative))
    for command in ["chrome", "chrome.exe", "msedge", "msedge.exe", "chromium", "chromium.exe", "google-chrome", "google-chrome-stable"]:
        found = shutil.which(command)
        if found:
            candidates.append(found)
    playwright_browsers = os.getenv("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / "AppData" / "Local" / "ms-playwright"))
    for channel_dir in ["chromium", "chrome", "msedge"]:
        p = Path(playwright_browsers) / channel_dir
        if p.is_dir():
            for exe in ["chrome.exe", "chrome-win" / "chrome.exe", "chrome-win64" / "chrome.exe"]:
                full = p / exe
                if full.exists():
                    candidates.append(str(full))

    result = []
    seen = set()
    for item in candidates:
        if not item:
            continue
        path = str(item)
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        if Path(path).exists():
            result.append(path)
    return result


def _get_proxy_from_env() -> str | None:
    return (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("ALL_PROXY")
        or os.environ.get("all_proxy")
    )


def launch_chromium_browser(playwright: Any, headless: bool = True, proxy: str | None = None) -> Any:
    args = [
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-setuid-sandbox",
        "--ignore-certificate-errors",
    ]
    launch_kwargs = {"headless": headless, "args": args}
    proxy = proxy or _get_proxy_from_env()
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}
    errors = []
    try:
        return playwright.chromium.launch(**launch_kwargs)
    except Exception as exc:
        errors.append(f"default: {exc}")
    for channel in ["chrome", "msedge"]:
        try:
            return playwright.chromium.launch(channel=channel, **launch_kwargs)
        except Exception as exc:
            errors.append(f"channel={channel}: {exc}")
    for executable_path in _browser_executable_candidates():
        try:
            return playwright.chromium.launch(executable_path=executable_path, **launch_kwargs)
        except Exception as exc:
            errors.append(f"{Path(executable_path).name}: {exc}")

    suggested_install = "python -m playwright install chromium"
    raise RuntimeError(
        "浏览器启动失败，未找到可用的 Chrome/Edge/Chromium。\n"
        f"请尝试：\n"
        f"  1. {suggested_install}\n"
        f"  2. 或安装 Chrome/Edge 浏览器\n"
        f"最后 3 个错误：{'; '.join(errors[-3:])}"
    )
