from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import streamlit as st

T = TypeVar("T")


class LoadingPlaceholder:
    """在长时间阻塞操作期间显示可更新的等待提示。"""

    def __init__(self, container=None) -> None:
        self._container = container
        self._box = None

    def show(self, message: str) -> None:
        text = message if message.startswith("⏳") else f"⏳ {message}"
        if self._box is None:
            parent = self._container if self._container is not None else st
            self._box = parent.empty()
        self._box.markdown(f"*{text}*")

    def clear(self) -> None:
        if self._box is not None:
            self._box.empty()
            self._box = None


def run_with_spinner(message: str, func: Callable[[], T]) -> T:
    with st.spinner(message):
        return func()
