from collections.abc import Iterator

import pytest

from src.limits import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> Iterator[None]:
    limiter.reset()
    yield
