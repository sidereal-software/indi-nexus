"""``INDI_NEXUS_*``: the environment an operator configures INDINexus with.

A container is configured by environment, not by editing the command line inside
it, so the knobs an operator actually reaches for - how chatty the log is, how
long the client waits for ``indiserver``, what token guards the write surface -
are readable from the environment under one prefix. :class:`Settings` is that
reader, and it is the **only** one: nothing else in the package calls
:func:`os.environ.get`, and no flag carries a Typer ``envvar=`` any more. One
variable, one reader, one place to look up what it means.

**Nothing reads this implicitly.** :class:`~indi_nexus.client.IndiClient`,
:class:`~indi_nexus.web.Bridge` and :func:`~indi_nexus.web.create_app` keep
explicit parameters with their present defaults; the *entrypoints* - the CLI
callback and :func:`indi_nexus.driver.run` - read the settings and pass the
values down. That is what keeps a library import free of ambient environment and
keeps every object injectable, which is what the whole test suite and
``create_app(client=...)`` depend on.

**This module imports nothing from ``driver/``, ``web/`` or ``client/``.** It is
imported by both the CLI and the driver's ``run()``, so any dependency it took
would become an edge in the import graph that ``tests/test_layering.py`` holds
flat.

Some of these settings also have a flag, and the rule between the two is one
rule everywhere: **an explicit flag beats the environment**, and the flag's
absence is what defers to it. :mod:`indi_nexus.cli` spells that out by giving
every such option a ``None`` default and resolving it in the command body, so
the environment is read when the command *runs* rather than when the module is
imported - a default evaluated at import time would freeze the first value the
process ever saw and make the precedence a lie under any in-process test runner.

:attr:`Settings.model_config` sets ``extra="ignore"``, and that is load-bearing
rather than tidy. The prefix is not reserved for this model: the test suite
already ships ``INDI_NEXUS_UPDATE_GOLDEN``, and an operator's own tooling may set
anything. Under pydantic's default ``forbid``, one such name in the environment
would raise out of :func:`settings` and take *every* entrypoint down - the CLI,
the bridge and every driver at once.
"""

from __future__ import annotations

import enum
from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class LogLevel(enum.StrEnum):
    """The log levels ``INDI_NEXUS_LOG_LEVEL`` and ``--log-level`` accept.

    A closed set rather than a free string, because the level is passed on to
    uvicorn as well as to :mod:`logging`, and uvicorn knows only these five. A
    typo is then a parse error naming the variable instead of a stack trace out
    of ``uvicorn.Config``.
    """

    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    DEBUG = "DEBUG"


def _upper(value: object) -> object:
    """Upper-case a string so ``INDI_NEXUS_LOG_LEVEL=debug`` is accepted.

    Parameters
    ----------
    value : object
        The raw value from the environment, or whatever a caller passed.

    Returns
    -------
    value : object
        The value upper-cased if it was a string, otherwise unchanged.
    """
    return value.upper() if isinstance(value, str) else value


def _split_origins(value: object) -> object:
    """Split ``INDI_NEXUS_ALLOWED_ORIGINS`` on whitespace into a list.

    An origin cannot contain whitespace, so a space-separated list needs no
    quoting and no escape. It is also what ``--allow-origin`` already accepted
    from the environment before this field existed - Click splits a repeatable
    option's environment value on whitespace - so a compose file written against
    the old behaviour keeps working. The default JSON decoding pydantic-settings
    applies to a collection field is suppressed with
    :class:`~pydantic_settings.NoDecode` for the same reason: an operator writes
    ``http://localhost:5173``, not ``["http://localhost:5173"]``.

    Parameters
    ----------
    value : object
        The raw value from the environment, or whatever a caller passed.

    Returns
    -------
    value : object
        The whitespace-separated words if it was a string, otherwise unchanged.
    """
    return value.split() if isinstance(value, str) else value


class Settings(BaseSettings):
    """The ``INDI_NEXUS_*`` environment, parsed and typed.

    Every default is the value the code already used before this model existed,
    so reading the settings changes no behaviour on its own. **They are the
    defaults for the flags too**, since the flags have none of their own: an
    option that also names a variable defaults to ``None`` and falls through to
    the field below, which is what stops a flag's default and a variable's from
    drifting apart.

    Attributes
    ----------
    log_level : LogLevel
        ``INDI_NEXUS_LOG_LEVEL``. The level :func:`configure_logging
        <indi_nexus.logging_config.configure_logging>` sets on the root logger,
        and the level uvicorn is started at.
    wire_log : bool
        ``INDI_NEXUS_WIRE_LOG``. Whether the ``indi_nexus.wire`` logger is turned
        up to DEBUG, which puts one line on stderr per INDI message in each
        direction.
    connect_timeout : float
        ``INDI_NEXUS_CONNECT_TIMEOUT``. Seconds
        :class:`~indi_nexus.client.IndiClient` waits for each connection attempt.
    reconnect_delay : float
        ``INDI_NEXUS_RECONNECT_DELAY``. Seconds between a lost connection and the
        next attempt.
    message_history : int
        ``INDI_NEXUS_MESSAGE_HISTORY``. How many recent INDI ``message`` frames
        the bridge replays to a newly attached browser.
    max_backlog : int
        ``INDI_NEXUS_MAX_BACKLOG``. How many live frames a browser may fall
        behind by before the bridge drops it.
    token : str
        ``INDI_NEXUS_TOKEN``, or ``serve --token``. The shared token ``/ws`` and
        ``/api`` require; ``""`` leaves both open, which is what a loopback
        development server wants.
    allowed_origins : tuple of str
        ``INDI_NEXUS_ALLOWED_ORIGINS``, or a repeated ``serve --allow-origin``.
        Browser origins accepted on ``/ws`` besides the server's own, **space
        separated** in the environment; ``"*"`` accepts any.
    allow_insecure_bind : bool
        ``INDI_NEXUS_ALLOW_INSECURE_BIND``, or ``serve --allow-insecure-bind``.
        Whether ``serve`` may bind a non-loopback host with no token.
    """

    model_config = SettingsConfigDict(env_prefix="INDI_NEXUS_", extra="ignore")

    log_level: Annotated[LogLevel, BeforeValidator(_upper)] = LogLevel.INFO
    wire_log: bool = False
    connect_timeout: float = 10.0
    reconnect_delay: float = 2.0
    message_history: int = 100
    max_backlog: int = 512
    token: str = ""
    allowed_origins: Annotated[tuple[str, ...], NoDecode, BeforeValidator(_split_origins)] = ()
    allow_insecure_bind: bool = False


@lru_cache(maxsize=1)
def settings() -> Settings:
    """Return the process's settings, read from the environment once.

    Cached because the environment does not change under a running process and
    every entrypoint would otherwise re-parse it. A test that manipulates the
    environment clears the cache with ``settings.cache_clear()``.

    Returns
    -------
    settings : Settings
        The parsed ``INDI_NEXUS_*`` environment.

    Raises
    ------
    pydantic.ValidationError
        Raised if a variable is present but does not parse as its type; the
        error names the variable.
    """
    return Settings()
