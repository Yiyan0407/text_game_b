"""asyncio 工具：供 Streamlit 同步入口与编排器使用。"""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """在同步上下文中运行 async 协程。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def gather_best_effort(*coros: Coroutine[Any, Any, Any]) -> list[Any]:
    """并发执行多个协程；单个失败不拖垮其余任务。"""
    if not coros:
        return []

    async def _safe(coro: Coroutine[Any, Any, Any]) -> Any:
        try:
            return await coro
        except Exception as exc:
            logger.warning("并发任务失败: %s", exc)
            return None

    return await asyncio.gather(*(_safe(c) for c in coros))
