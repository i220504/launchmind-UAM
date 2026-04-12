from __future__ import annotations

import time
from typing import Callable, TypeVar

from config import settings

T = TypeVar("T")


def retry_call(
    func: Callable[[], T],
    *,
    attempts: int | None = None,
    backoff_seconds: int | None = None,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    max_attempts = attempts or settings.retry_attempts
    backoff = backoff_seconds or settings.retry_backoff_seconds
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except retry_on as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            time.sleep(backoff * attempt)
    if last_error is None:
        raise RuntimeError("retry_call failed without capturing an exception")
    raise last_error
