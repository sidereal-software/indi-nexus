"""Shared pytest configuration for the INDIkit test suite."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from typer import rich_utils

# Wide enough that no flag, environment-variable name or refusal message the CLI
# tests match on can wrap. Typer's widest help row here is well inside it, and it
# matches the repository's own line length.
CLI_HELP_WIDTH = 100


@pytest.fixture(autouse=True, scope="session")
def _deterministic_cli_rendering() -> Iterator[None]:
    """Render Typer's help and error panels identically everywhere.

    Typer builds its Rich console from two module-level constants, and both of
    them read the ambient environment. ``MAX_WIDTH`` is unset unless
    ``TERMINAL_WIDTH`` is exported, so Rich falls back to the terminal's width and
    wraps to fit it; ``FORCE_TERMINAL`` is switched on by the mere presence of
    ``GITHUB_ACTIONS``, ``FORCE_COLOR`` or ``PY_COLORS``, which makes Rich emit
    colour into a pipe that has no terminal on the end of it.

    Either one breaks a test that matches on what an operator reads. Wrapping
    splits a long flag mid-name, so ``--allow-insecure-bind`` arrives as
    ``--allow-insecure-`` and ``bind`` on the next line. Colour is worse, because
    Rich styles the leading dash separately and even an unwrapped ``--token`` comes
    back as two escape-separated runs. Neither is visible to a developer on a wide
    terminal, and both are guaranteed on a CI runner.

    Pinning both here rather than in one test keeps every assertion about
    user-facing CLI output deterministic, including ones not yet written. The
    assertions themselves still run against the rendered text, so dropping a flag
    from the help still fails.

    Yields
    ------
    None
        For the duration of the test session, with both constants restored after.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(rich_utils, "FORCE_TERMINAL", False)
        patch.setattr(rich_utils, "MAX_WIDTH", CLI_HELP_WIDTH)
        yield
