import re

from game.models import ChatMessage, GameState


class ConversationWindowMemory:
    """滑动窗口记忆：保留最近 N 条消息。"""

    def __init__(self, window_size: int = 40):
        self.window_size = window_size

    def get_history(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        if len(messages) <= self.window_size:
            return list(messages)
        return messages[-self.window_size :]

    @staticmethod
    def format_for_summary(messages: list[ChatMessage], max_messages: int = 24) -> str:
        recent = messages[-max_messages:] if len(messages) > max_messages else messages
        lines: list[str] = []
        for msg in recent:
            if msg.role == "system":
                prefix = "【系统】"
            elif msg.role == "user":
                prefix = "【玩家】"
            else:
                prefix = "【KP】"
            lines.append(f"{prefix} {msg.content}")
        return "\n\n".join(lines)

    @staticmethod
    def slice_since_turn(messages: list[ChatMessage], since_index: int) -> list[ChatMessage]:
        """按消息条数近似切分（每回合约 2-3 条消息）。"""
        if since_index <= 0:
            return messages
        # since_index 在这里表示「从第 N 条消息开始」，由调用方换算
        return messages[since_index:] if since_index < len(messages) else []
