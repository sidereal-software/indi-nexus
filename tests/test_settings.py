"""Tests for the ``INDIKIT_*`` environment model.

The names here are a 1.0 contract - an operator writes them into a compose file -
so the defaults are pinned to the values the code used before the model existed,
and the prefix is checked to tolerate a name this model does not know.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from indikit.settings import LogLevel, Settings, settings


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    """Remove every ``INDIKIT_*`` variable and drop the cached settings.

    The developer running the suite may well have some of these set, and
    :func:`settings` is cached for the life of the process.
    """
    for name in [key for key in dict(os.environ) if key.startswith("INDIKIT_")]:
        monkeypatch.delenv(name, raising=False)
    settings.cache_clear()
    yield
    settings.cache_clear()


def test_the_defaults_are_todays_values():
    """An empty environment reproduces the constants the code already used."""
    config = Settings()
    assert config.log_level == LogLevel.INFO
    assert config.wire_log is False
    # client/client.py's IndiClient defaults.
    assert config.connect_timeout == 10.0
    assert config.reconnect_delay == 2.0
    # web/bridge.py's _MESSAGE_HISTORY and _MAX_BACKLOG.
    assert config.message_history == 100
    assert config.max_backlog == 512
    # `serve`'s access control, open by default so a loopback dev server just runs.
    assert config.token == ""
    assert config.allowed_origins == ()
    assert config.allow_insecure_bind is False


def test_every_name_parses_to_its_type(monkeypatch):
    """Each variable is read under the prefix and coerced to its field type."""
    monkeypatch.setenv("INDIKIT_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("INDIKIT_WIRE_LOG", "1")
    monkeypatch.setenv("INDIKIT_CONNECT_TIMEOUT", "3.5")
    monkeypatch.setenv("INDIKIT_RECONNECT_DELAY", "0.25")
    monkeypatch.setenv("INDIKIT_MESSAGE_HISTORY", "7")
    monkeypatch.setenv("INDIKIT_MAX_BACKLOG", "9")
    monkeypatch.setenv("INDIKIT_TOKEN", "secret")
    monkeypatch.setenv("INDIKIT_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("INDIKIT_ALLOW_INSECURE_BIND", "1")
    config = Settings()
    assert config.log_level is LogLevel.WARNING
    assert config.wire_log is True
    assert config.connect_timeout == 3.5
    assert config.reconnect_delay == 0.25
    assert config.message_history == 7
    assert config.max_backlog == 9
    assert config.token == "secret"
    assert config.allowed_origins == ("http://localhost:5173",)
    assert config.allow_insecure_bind is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://a http://b", ("http://a", "http://b")),
        # The Docker entrypoint and a hand-written compose file both produce this.
        ("  http://a   http://b  ", ("http://a", "http://b")),
        ("*", ("*",)),
        ("", ()),
    ],
)
def test_allowed_origins_is_space_separated(monkeypatch, raw, expected):
    """The environment form is whitespace-separated, not JSON.

    An origin cannot contain whitespace, so this needs no quoting - and it is
    what ``--allow-origin`` already read from the environment through Click,
    so a compose file written against the old behaviour keeps working. Without
    ``NoDecode`` pydantic-settings would try to JSON-decode a collection field
    and reject every one of these.
    """
    monkeypatch.setenv("INDIKIT_ALLOWED_ORIGINS", raw)
    assert Settings().allowed_origins == expected


def test_allowed_origins_accepts_a_list_from_python():
    """Constructed by hand, the field takes the sequence it looks like.

    ``serve`` hands the repeated ``--allow-origin`` values around as a tuple, so
    the string-splitting path must not be the only one that works.
    """
    assert Settings(allowed_origins=["http://a", "http://b"]).allowed_origins == (
        "http://a",
        "http://b",
    )


def test_a_lowercase_log_level_is_accepted(monkeypatch):
    """``INDIKIT_LOG_LEVEL=debug`` is what somebody will actually type."""
    monkeypatch.setenv("INDIKIT_LOG_LEVEL", "debug")
    assert Settings().log_level is LogLevel.DEBUG


def test_a_malformed_value_names_the_variable(monkeypatch):
    """A value that will not parse fails loudly, saying which one it was."""
    monkeypatch.setenv("INDIKIT_RECONNECT_DELAY", "2.0s")
    with pytest.raises(ValidationError, match="reconnect_delay"):
        Settings()


def test_an_unknown_log_level_is_refused(monkeypatch):
    """The level is a closed set, because uvicorn is started at it too."""
    monkeypatch.setenv("INDIKIT_LOG_LEVEL", "CHATTY")
    with pytest.raises(ValidationError, match="log_level"):
        Settings()


def test_other_prefixed_names_are_ignored(monkeypatch):
    """A prefixed name this model does not know is not an error.

    ``extra="ignore"`` is load-bearing rather than tidy. The prefix is not
    reserved for this model - this suite ships ``INDIKIT_UPDATE_GOLDEN``, and
    an operator's own tooling may set anything - and under the default ``forbid``
    one such name would raise out of every entrypoint at once: the CLI, the
    bridge and every driver.
    """
    monkeypatch.setenv("INDIKIT_UPDATE_GOLDEN", "1")
    monkeypatch.setenv("INDIKIT_SOMETHING_A_LATER_VERSION_ADDS", "x")
    assert Settings().log_level is LogLevel.INFO


def test_config_dir_is_taken_from_the_variable_first(monkeypatch, tmp_path):
    """``INDIKIT_CONFIG_DIR`` wins over the computed default."""
    monkeypatch.setenv("HOME", "/home/observer")
    monkeypatch.setenv("INDIKIT_CONFIG_DIR", str(tmp_path))
    assert Settings().config_dir == tmp_path


def test_config_dir_defaults_to_the_posix_app_directory(monkeypatch):
    """With no variable of ours, it is ``~/.indikit``, expanded from HOME.

    ``click.get_app_dir(..., force_posix=True)`` gives that answer on Linux and
    macOS alike, which is the point: one path on every machine an operator
    administers, and it sits beside libindi's own ``~/.indi``.
    """
    monkeypatch.setenv("HOME", "/home/observer")
    assert Settings().config_dir == Path("/home/observer/.indikit")


def test_config_dir_ignores_xdg_config_home(monkeypatch):
    """``XDG_CONFIG_HOME`` is deliberately **not** honoured. Do not "fix" this.

    It is what ``force_posix=True`` costs, and it was taken knowingly: the same
    path everywhere beats obeying a variable one platform of the three defines.
    ``INDIKIT_CONFIG_DIR`` is the supported way to move the directory, and it
    is what the ``ConfigError`` names.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg")
    monkeypatch.setenv("HOME", "/home/observer")
    assert Settings().config_dir == Path("/home/observer/.indikit")


def test_config_dir_is_none_when_there_is_no_home(monkeypatch):
    """No resolvable home is `None`, not a raise and not a temporary directory.

    A service manager runs a driver with no ``HOME``, and both alternatives are
    worse than admitting it: ``Path.home()`` raises there, taking down a driver
    that was never going to save anything, and a temp directory would accept
    every save and lose the lot at the next reboot without a word. The third
    wrong answer is the one this default now has to guard against on its own:
    ``os.path.expanduser`` leaves the ``~`` in place instead of raising, so an
    unguarded ``click.get_app_dir`` hands back the relative ``~/.indikit``
    and a driver saves into its working directory.
    """
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    # expanduser consults the password database when HOME is unset, which on a
    # developer's machine still answers; pwd is where that lookup lands.
    monkeypatch.setattr("pwd.getpwuid", lambda _uid: (_ for _ in ()).throw(KeyError("no such uid")))
    assert Settings().config_dir is None


def test_the_config_dir_default_is_not_evaluated_at_import(monkeypatch):
    """The default is a factory, so the environment is read when the model is.

    A default computed in the field's signature is evaluated at *import* and
    freezes the first home the process ever saw, which under any in-process
    runner makes the variable's precedence a lie.
    """
    monkeypatch.setenv("HOME", "/home/first")
    assert Settings().config_dir == Path("/home/first/.indikit")
    monkeypatch.setenv("HOME", "/home/second")
    assert Settings().config_dir == Path("/home/second/.indikit")


def test_settings_is_read_once(monkeypatch):
    """The accessor caches, and a test can clear it."""
    monkeypatch.setenv("INDIKIT_MAX_BACKLOG", "11")
    assert settings().max_backlog == 11
    monkeypatch.setenv("INDIKIT_MAX_BACKLOG", "12")
    assert settings().max_backlog == 11
    settings.cache_clear()
    assert settings().max_backlog == 12
