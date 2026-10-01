from typing import ClassVar, Literal
from urllib.parse import urlsplit

from maibot_sdk import Field, PluginConfigBase
from pydantic import field_validator


def parse_mappings(items: list[str]) -> dict[str, str]:
    mappings = {}
    for row_number, item in enumerate(items, start=1):
        command, separator, url = item.partition("=>")
        command = command.strip()
        url = url.strip()
        if not separator or not command or not url:
            raise ValueError(f"第 {row_number} 项必须使用“特定指令 => 网页链接”格式")
        if any(character in command for character in "\r\n\x00"):
            raise ValueError(f"第 {row_number} 项的指令不能包含换行或空字符")
        if command in mappings:
            raise ValueError(f"第 {row_number} 项的指令重复")
        try:
            parsed_url = urlsplit(url)
            valid_url = (
                parsed_url.scheme in {"http", "https"}
                and parsed_url.hostname
                and parsed_url.port != 0
                and parsed_url.username is None
                and parsed_url.password is None
                and not any(character.isspace() or ord(character) < 32 for character in url)
            )
        except ValueError:
            valid_url = False
        if not valid_url:
            raise ValueError(f"第 {row_number} 项必须是无内嵌账号密码的 HTTP/HTTPS 链接")
        mappings[command] = url
    return mappings


class PluginSection(PluginConfigBase):
    __ui_label__: ClassVar[str] = "基础设置"
    __ui_order__: ClassVar[int] = 0

    config_version: str = Field(default="1.1.0", description="配置结构版本，请勿手动修改")
    enabled: bool = Field(default=True, description="是否启用网页截图插件")


class CommandsSection(PluginConfigBase):
    __ui_label__: ClassVar[str] = "指令映射"
    __ui_order__: ClassVar[int] = 1

    mappings: list[str] = Field(
        default_factory=list,
        description="每行一组：特定指令 => 网页链接",
        json_schema_extra={
            "label": "指令列表（每行一组）",
            "hint": "例如：/官网 => https://example.com\n默认包含匹配；增删指令或切换匹配方式后请重新加载插件。",
            "placeholder": "/官网 => https://example.com",
            "order": 0,
        },
    )

    match_mode: Literal["contains", "exact"] = Field(
        default="contains",
        description="contains：包含匹配；exact：完整匹配",
        json_schema_extra={
            "label": "指令匹配方式",
            "hint": "包含匹配：消息中出现指令即可触发；完整匹配：消息去除首尾空白后必须等于指令。切换后请重新加载插件。",
            "order": 1,
        },
    )

    @field_validator("mappings")
    @classmethod
    def validate_mappings(cls, items: list[str]) -> list[str]:
        parse_mappings(items)
        return items


class WebScreenshotConfig(PluginConfigBase):
    plugin: PluginSection = Field(default_factory=PluginSection)
    commands: CommandsSection = Field(default_factory=CommandsSection)
