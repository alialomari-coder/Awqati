"""Small synchronous dispatcher for lightweight application events."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import TypeVar

from ..domain import DomainEvent


EventType = TypeVar("EventType", bound=DomainEvent)


class EventDispatcher:
	"""Publish typed events without coupling a use case to future consumers."""

	def __init__(self) -> None:
		self._listeners: dict[type[DomainEvent], list[Callable[[DomainEvent], None]]] = defaultdict(list)

	def subscribe(self, event_type: type[EventType], listener: Callable[[EventType], None]) -> Callable[[], None]:
		listeners = self._listeners[event_type]
		listeners.append(listener)  # type: ignore[arg-type]

		def unsubscribe() -> None:
			if listener in listeners:
				listeners.remove(listener)  # type: ignore[arg-type]

		return unsubscribe

	def publish(self, event: DomainEvent) -> None:
		for listener in tuple(self._listeners.get(type(event), ())):
			listener(event)
