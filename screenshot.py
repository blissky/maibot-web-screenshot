from pathlib import Path
from typing import Any

import asyncio
import base64
import shutil

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


class ScreenshotError(RuntimeError):
    pass


def _resolve_browser_path(config: dict[str, Any], default_executable: str) -> str:
    configured_path = config["executable_path"].strip()
    if configured_path:
        executable = Path(configured_path).expanduser()
        if not executable.is_file():
            raise ScreenshotError("MaiBot 配置的浏览器可执行文件不存在，请检查 executable_path。")
        return str(executable.resolve())

    default_path = Path(default_executable)
    cache_root = Path(config["browser_install_root"].strip() or "data/playwright-browsers").expanduser()
    for directory in default_path.parents:
        if directory.name.startswith("chromium-"):
            cached_executable = cache_root / default_path.relative_to(directory.parent)
            if cached_executable.is_file():
                return str(cached_executable.resolve())
            break

    executable_names = {
        "chrome", "chrome.exe", "headless_shell", "headless_shell.exe",
        "chrome-headless-shell", "chrome-headless-shell.exe",
        "Chromium", "Google Chrome for Testing",
    }
    candidates = [
        candidate for candidate in cache_root.glob("chrom*/**/*")
        if candidate.name in executable_names and candidate.is_file()
    ]
    if candidates:
        executable = max(candidates, key=lambda candidate: candidate.stat().st_mtime)
        return str(executable.resolve())

    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "msedge"):
        executable = shutil.which(name)
        if executable:
            return executable
    if default_path.is_file():
        return str(default_path)
    raise ScreenshotError("未找到 Chromium，请在 MaiBot 浏览器配置中设置可用的 executable_path 或准备好浏览器缓存。")


async def capture_page(url: str, config: dict[str, Any]) -> str:
    if not config["enabled"]:
        raise ScreenshotError("MaiBot 浏览器渲染能力已禁用，请先启用。")

    async with async_playwright() as playwright:
        try:
            endpoint = config["browser_ws_endpoint"].strip()
            timeout_ms = int(config["startup_timeout_sec"] * 1000)
            if endpoint:
                browser = await playwright.chromium.connect_over_cdp(endpoint, timeout=timeout_ms)
            else:
                executable_path = await asyncio.to_thread(
                    _resolve_browser_path, config, playwright.chromium.executable_path
                )
                browser = await playwright.chromium.launch(
                    executable_path=executable_path,
                    args=config["launch_args"],
                    headless=config["headless"],
                    timeout=timeout_ms,
                )
            try:
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    device_scale_factor=1,
                    locale="zh-CN",
                    accept_downloads=False,
                )
                try:
                    page = await context.new_page()
                    page.set_default_timeout(30000)
                    response = await page.goto(url, wait_until="load", timeout=30000)
                    if response is None or response.status >= 400:
                        raise ScreenshotError("网页返回错误响应，请检查配置的链接。")
                    await page.evaluate("() => document.fonts.ready")
                    await page.wait_for_timeout(2000)
                    image_bytes = await page.screenshot(
                        full_page=True,
                        type="png",
                        animations="disabled",
                        timeout=30000,
                    )
                    return base64.b64encode(image_bytes).decode("ascii")
                finally:
                    await context.close()
            finally:
                if not endpoint:
                    await browser.close()
        except PlaywrightTimeoutError as error:
            raise TimeoutError("浏览器启动、网页加载或截图超时") from error
