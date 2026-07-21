from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel

from sanjiv.contracts import MetricEnvelope


def iter_metrics(value: Any, path: str = "plan") -> Iterator[tuple[str, MetricEnvelope[Any]]]:
    if isinstance(value, MetricEnvelope):
        yield path, value
        return
    if isinstance(value, BaseModel):
        for name in value.__class__.model_fields:
            yield from iter_metrics(getattr(value, name), f"{path}.{name}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield from iter_metrics(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from iter_metrics(item, f"{path}[{index}]")
