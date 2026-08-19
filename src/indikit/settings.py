"""``INDIKIT_*``: the environment an operator configures INDIkit with.

A container is configured by environment, not by editing the command line inside
it, so the knobs an operator actually reaches for - how chatty the log is, how
long the client waits for ``indiserver``, what token guards the write surface -
are readable from the environment under one prefix. :class:`Settings` is that
reader, and it is the **only** one: nothing else in the package calls
:func:`os.environ.get`, and no flag carries a Typer ``envvar=`` any more. One
variable, one reader, one place to look up what it means.

**Nothing reads this implicitly.** :class:`~indikit.client.IndiClient`,
:class:`~indikit.web.Bridge` and :func:`~indikit.web.create_app` keep
explicit parameters with their present defaults; the *entrypoints* - the CLI
callback and :func:`indikit.driver.run` - read the settings and pass the
values down. That is what keeps a library import free of ambient environment and
keeps every object injectable, which is what the whole test suite and
``create_app(client=...)`` depend on.

**This module imports nothing from ``driver/``, ``web/`` or ``client/``.** It is
imported by both the CLI and the driver's ``run()``, so any dependency it took
would become an edge in the import graph that ``tests/test_layering.py`` holds
flat.

Some of these settings also have a flag, and the rule between the two is one
rule everywhere: **an explicit flag beats the environment**, and the flag's
absence is what defers to it. :mod:`indikit.cli` spells that out by giving
every such option a ``None`` default and resolving it in the command body, so
the environment is read when the command *runs* rather than when the module is
imported - a default evaluated at import time would freeze the first value the
process ever saw and make the precedence a lie under any in-process test runner.

:attr:`Settings.model_config` sets ``extra="ignore"``, and that is load-bearing
rather than tidy. The prefix is not reserved for this model: the test suite
already ships ``INDIKIT_UPDATE_GOLDEN``, and an operator's own tooling may set
anything. Under pydantic's default ``forbid``, one such name in the environment
would raise out of :func:`settings` and take *every* entrypoint down - the CLI,
the bridge and every driver at once.
"""

from __future__ import annotations

import enum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import click
from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class LogLevel(enum.StrEnum):
    """The log levels ``INDIKIT_LOG_LEVEL`` and ``--log-level`` accept.

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
    """Upper-case a string so ``INDIKIT_LOG_LEVEL=debug`` is accepted.

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
    """Split ``INDIKIT_ALLOWED_ORIGINS`` on whitespace into a list.

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


def _default_config_dir() -> Path | None:
    """Return the directory a driver saves its configuration under.

    :func:`click.get_app_dir` decides it, with ``force_posix=True``, so the
    answer is ``~/.indikit`` on Linux and macOS alike. Click is already a
    hard dependency through Typer, and where an application's configuration
    belongs is not a problem worth solving here.

    ``force_posix`` is the whole decision, and it buys two things. An operator
    administering several machines reads and edits the same path on all of them,
    rather than ``~/.config`` here and ``~/Library/Application Support`` there.
    And ``~/.indikit`` sits directly beside libindi's own ``~/.indi``, so both
    halves of one observatory's configuration are in one place - beside it, not
    *in* it, because a file of ours under libindi's name would leave two
    frameworks fighting over one path with different schemas.

    **It costs the XDG variable.** ``force_posix=True`` ignores
    ``XDG_CONFIG_HOME``, which the previous chain honoured, so a Linux user who
    sets it is no longer obeyed. ``INDIKIT_CONFIG_DIR`` is the escape hatch
    and is the supported way to put the directory anywhere else. Windows is the
    other place the name does not hold: Click resolves an ``indikit`` folder
    under ``%APPDATA%`` there and never reaches its ``force_posix`` branch.

    ``None`` is a real answer, and the important one. A process with no
    resolvable home is how a service manager runs a driver, and both obvious
    alternatives are worse than admitting it: :meth:`pathlib.Path.home` *raises*
    there, taking down a driver that was never going to save anything, and a
    temporary directory would accept every save and lose the lot on reboot
    without a word. ``None`` makes the persistence methods raise
    :class:`~indikit.ConfigError` naming ``INDIKIT_CONFIG_DIR`` as the fix.

    Returns
    -------
    directory : Path or None
        ``~/.indikit``, or `None` when the home directory cannot be expanded.
    """
    directory = Path(click.get_app_dir("indikit", force_posix=True))
    # Click builds that path with os.path.expanduser, which leaves a leading "~"
    # in place when there is nothing to expand it with rather than raising, so
    # the result is relative exactly when the home did not resolve. Handing it
    # back would have a driver save into whatever directory it happened to be
    # started from - the case the None branch above exists for.
    if not directory.is_absolute():
        return None
    return directory


class Settings(BaseSettings):
    """The ``INDIKIT_*`` environment, parsed and typed.

    Every default is the value the code already used before this model existed,
    so reading the settings changes no behaviour on its own. **They are the
    defaults for the flags too**, since the flags have none of their own: an
    option that also names a variable defaults to ``None`` and falls through to
    the field below, which is what stops a flag's default and a variable's from
    drifting apart.

    Attributes
    ----------
    log_level : LogLevel
        ``INDIKIT_LOG_LEVEL``. The level :func:`configure_logging
        <indikit.logging_config.configure_logging>` sets on the root logger,
        and the level uvicorn is started at.
    wire_log : bool
        ``INDIKIT_WIRE_LOG``. Whether the ``indikit.wire`` logger is turned
        up to DEBUG, which puts one line on stderr per INDI message in each
        direction.
    connect_timeout : float
        ``INDIKIT_CONNECT_TIMEOUT``. Seconds
        :class:`~indikit.client.IndiClient` waits for each connection attempt.
    reconnect_delay : float
        ``INDIKIT_RECONNECT_DELAY``. Seconds between a lost connection and the
        next attempt.
    message_history : int
        ``INDIKIT_MESSAGE_HISTORY``. How many recent INDI ``message`` frames
        the bridge replays to a newly attached browser.
    max_backlog : int
        ``INDIKIT_MAX_BACKLOG``. How many live frames a browser may fall
        behind by before the bridge drops it.
    token : str
        ``INDIKIT_TOKEN``, or ``serve --token``. The shared token ``/ws`` and
        ``/api`` require; ``""`` leaves both open, which is what a loopback
        development server wants.
    allowed_origins : tuple of str
        ``INDIKIT_ALLOWED_ORIGINS``, or a repeated ``serve --allow-origin``.
        Browser origins accepted on ``/ws`` besides the server's own, **space
        separated** in the environment; ``"*"`` accepts any.
    allow_insecure_bind : bool
        ``INDIKIT_ALLOW_INSECURE_BIND``, or ``serve --allow-insecure-bind``.
        Whether ``serve`` may bind a non-loopback host with no token.
    config_dir : Path or None
        ``INDIKIT_CONFIG_DIR``. Where a driver's ``CONFIG_PROCESS`` saves and
        loads its properties, defaulting to ``~/.indikit`` per
        :func:`_default_config_dir` - which does not consult ``XDG_CONFIG_HOME``,
        so this variable is how the directory is moved. `None` means there is
        nowhere to save, and the persistence methods say so.
    """

    model_config = SettingsConfigDict(env_prefix="INDIKIT_", extra="ignore")

    log_level: Annotated[LogLevel, BeforeValidator(_upper)] = LogLevel.INFO
    wire_log: bool = False
    connect_timeout: float = 10.0
    reconnect_delay: float = 2.0
    message_history: int = 100
    max_backlog: int = 512
    token: str = ""
    allowed_origins: Annotated[tuple[str, ...], NoDecode, BeforeValidator(_split_origins)] = ()
    allow_insecure_bind: bool = False
    # default_factory, never a computed default in the signature: the latter is
    # evaluated at import and would freeze the first environment the process saw.
    config_dir: Path | None = Field(default_factory=_default_config_dir)


@lru_cache(maxsize=1)
def settings() -> Settings:
    """Return the process's settings, read from the environment once.

    Cached because the environment does not change under a running process and
    every entrypoint would otherwise re-parse it. A test that manipulates the
    environment clears the cache with ``settings.cache_clear()``.

    Returns
    -------
    settings : Settings
        The parsed ``INDIKIT_*`` environment.

    Raises
    ------
    pydantic.ValidationError
        Raised if a variable is present but does not parse as its type; the
        error names the variable.
    """
    return Settings()
