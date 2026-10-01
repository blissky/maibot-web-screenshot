import asyncio
import re
from typing import Any

from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Command, MaiBotPlugin

from .config import WebScreenshotConfig, parse_mappings
from .screenshot import ScreenshotError, capture_page


class WebScreenshotPlugin(MaiBotPlugin):
    config_model = WebScreenshotConfig

    def __init__(self) -> None:
        super().__init__()
        self._command_urls: dict[str, str] = {}
        self._registered_commands: frozenset[str] = frozenset()
        self._registered_match_mode = ""
        self._capture_lock = asyncio.Lock()

    def get_components(self) -> list[dict[str, Any]]:
        self._command_urls = parse_mappings(self.config.commands.mappings)
        self._registered_commands = frozenset(self._command_urls)
        self._registered_match_mode = self.config.commands.match_mode
        pattern = r"(?!)"
        if self.config.plugin.enabled and self._command_urls:
            alternatives = "|".join(
                re.escape(command) for command in sorted(self._command_urls, key=len, reverse=True)
            )
            pattern = rf"(?P<command>{alternatives})"
            if self.config.commands.match_mode == "exact":
                pattern = rf"\A\s*{pattern}\s*\Z"
        components = []
        for component in super().get_components():
            if component["name"] == "web_screenshot":
                component = {
                    **component,
                    "metadata": {**component["metadata"], "command_pattern": pattern},
                }
            components.append(component)
        return components

    async def on_load(self) -> None:
        self.ctx.logger.info("网页截图插件已加载，配置了 %d 条指令", len(self._command_urls))

    async def on_unload(self) -> None:
        async with self._capture_lock:
            self._command_urls.clear()

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        if scope == CONFIG_RELOAD_SCOPE_SELF:
            self._command_urls = parse_mappings(self.config.commands.mappings)
            if (
                frozenset(self._command_urls) != self._registered_commands
                or self.config.commands.match_mode != self._registered_match_mode
            ):
                self.ctx.logger.warning("截图指令列表或匹配方式已变更，请重新加载插件以更新命令匹配规则")

    @Command(
        "web_screenshot",
        description="截取配置链接的整个网页并发送到当前聊天",
        pattern=r"(?!)",
        timeout_ms=60000,
    )
    async def handle_screenshot(
        self, stream_id: str = "", matched_groups: dict | None = None, **kwargs
    ) -> tuple[bool, str | None, int]:
        if not self.config.plugin.enabled:
            return False, None, 0
        command = (matched_groups or {}).get("command", "")
        url = self._command_urls.get(command)
        if url is None:
            return False, None, 0
        if not stream_id:
            return False, "无法确定当前聊天", 0
        if self._capture_lock.locked():
            await self.ctx.send.text("正在截取网页，请稍后再试。", stream_id)
            return False, "截图任务繁忙", 2
        async with self._capture_lock:
            try:
                async with asyncio.timeout(45):
                    defaults = {
                        "enabled": True,
                        "browser_install_root": "data/playwright-browsers",
                        "executable_path": "",
                        "browser_ws_endpoint": "",
                        "headless": True,
                        "launch_args": [],
                        "startup_timeout_sec": 20.0,
                    }
                    values = await asyncio.gather(
                        *(
                            self.ctx.config.get(f"plugin_runtime.render.{key}", default)
                            for key, default in defaults.items()
                        )
                    )
                    image_base64 = await capture_page(url, dict(zip(defaults, values)))
                if not image_base64:
                    raise RuntimeError("浏览器未返回图片数据")
                sent = await self.ctx.send.image(image_base64, stream_id)
                if not sent:
                    await self.ctx.send.text("网页已截图，但图片发送失败，请检查聊天平台限制。", stream_id)
                    return False, "图片发送失败", 2
                return True, "整页截图已发送", 2
            except TimeoutError:
                await self.ctx.send.text("网页加载或截图超时，未发送不完整截图，请稍后再试。", stream_id)
                return False, "网页截图超时", 2
            except ScreenshotError as error:
                self.ctx.logger.warning("网页截图失败：%s", error)
                await self.ctx.send.text(f"网页截图失败：{error}", stream_id)
                return False, "网页截图失败", 2
            except Exception as error:
                self.ctx.logger.error("网页截图失败（%s）", type(error).__name__)
                await self.ctx.send.text(
                    "网页截图失败，请检查链接是否可访问，以及 MaiBot 运行环境中的 Playwright 和 Chromium 是否已准备完成。",
                    stream_id,
                )
                return False, "网页截图失败", 2


def create_plugin() -> WebScreenshotPlugin:
    return WebScreenshotPlugin()
