"""Background worker service for offloading non-critical tasks."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

class BackgroundWorker(ABC):
    """Abstract interface for background task scheduling."""
    
    @abstractmethod
    def enqueue(self, task: Callable[..., Coroutine[Any, Any, Any]], *args: Any, **kwargs: Any) -> None:
        """Enqueue an asynchronous task to run in the background."""
        pass


class AsyncioBackgroundWorker(BackgroundWorker):
    """A simple asyncio-based background worker.
    
    Suitable for single-instance deployments. For distributed setups,
    this should be replaced with a Celery/Redis implementation.
    """
    
    def enqueue(self, task: Callable[..., Coroutine[Any, Any, Any]], *args: Any, **kwargs: Any) -> None:
        async def _wrapper() -> None:
            try:
                await task(*args, **kwargs)
            except Exception as e:
                logger.error(f"Background task {task.__name__} failed: {e}", exc_info=True)
                
        asyncio.create_task(_wrapper())

# Global instance
background_worker = AsyncioBackgroundWorker()
