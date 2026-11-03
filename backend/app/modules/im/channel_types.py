from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImChannelType:
    key: str
    label: str
    enabled: bool
    description: str


CHANNEL_TYPES: tuple[ImChannelType, ...] = (
    ImChannelType(
        key="websocket",
        label="WebSocket",
        enabled=True,
        description="Browser WebSocket channel with exact Origin allowlisting",
    ),
    ImChannelType(
        key="feishu",
        label="飞书",
        enabled=False,
        description="飞书 adapter is not installed",
    ),
    ImChannelType(
        key="dingtalk",
        label="钉钉",
        enabled=False,
        description="钉钉 adapter is not installed",
    ),
    ImChannelType(
        key="wecom",
        label="企业微信",
        enabled=False,
        description="企业微信 adapter is not installed",
    ),
)


def get_channel_type(key: str) -> ImChannelType | None:
    return next((item for item in CHANNEL_TYPES if item.key == key), None)
