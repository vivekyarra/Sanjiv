from collections.abc import AsyncIterator
from typing import Protocol

from sanjiv.contracts import DataMode
from sanjiv.maritime.contracts import AdapterHealth, RawAISMessage


class AISSourceAdapter(Protocol):
    """Provider-neutral asynchronous AIS source."""

    @property
    def source_id(self) -> str: ...

    @property
    def mode(self) -> DataMode: ...

    async def health(self) -> AdapterHealth: ...

    def stream(self) -> AsyncIterator[RawAISMessage]: ...
