"""The ``@on_new`` decorator: route client writes to typed handlers.

pyINDI made a driver override ``ISNewNumber`` / ``ISNewText`` / ``ISNewSwitch``
and then hand-dispatch on the property name with an ``if/elif`` chain over raw
XML tags. Here a handler is tagged with the property name it serves; the device
builds a per-instance ``name -> handler`` map and hands each incoming
``newXxxVector`` to the matching handler as a fully typed, parsed vector.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, TypeVar

_HANDLER_ATTR = "__indi_on_new__"

F = TypeVar("F", bound=Callable[..., Any])


def on_new(name: str) -> Callable[[F], F]:
    """Register the decorated method as the handler for client writes to ``name``.

    The handler receives the parsed vector for the property the client is trying
    to change::

        @on_new("CONNECTION")
        async def _connect(self, vector: SwitchVector) -> None:
            connect = vector["CONNECT"].value == ISState.ON
            ...
    """

    def decorator(func: F) -> F:
        setattr(func, _HANDLER_ATTR, name)
        return func

    return decorator


def iter_new_handlers(obj: object) -> Iterator[tuple[str, Callable[..., Any]]]:
    """Yield ``(property_name, bound_method)`` for each ``@on_new`` handler on ``obj``."""
    seen: set[str] = set()
    for klass in type(obj).__mro__:
        for attr, value in vars(klass).items():
            if attr in seen:
                continue
            seen.add(attr)
            prop_name = getattr(value, _HANDLER_ATTR, None)
            if isinstance(prop_name, str):
                yield prop_name, getattr(obj, attr)
