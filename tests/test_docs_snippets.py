"""Every code fence in the published documentation, checked against the code.

The documentation is the first thing anyone runs, and until this module existed
almost none of it was executed by anything. A snippet that stopped matching the
package was found by a reader pasting it, which is the worst place to find it.

Nothing here keeps a copy of a snippet. Each fence is read out of the markdown
**at test time** (``tests/docs_fences.py``), so there is no second copy to fall
out of step: the only way to change what is checked is to change the page.

Four things can be true of a fence, and :data:`CLAIMS` says which, per fence, for
every fence on every page. A fence nothing claims fails
:func:`test_every_python_fence_is_accounted_for`, so a new snippet cannot arrive
unexamined.

``RUNS``
    Complete enough to execute. It is executed, usually through
    :class:`~indi_nexus.testing.DeviceHarness`, and the page's claims about what
    it does are asserted.
``EXCERPT``
    A trimmed quotation of a real file. Every statement it shows, with every
    argument it shows, has to be in that file - see
    :func:`~tests.docs_fences.contains_snippet`.
``COMPILES``
    A fragment with no runnable form: it is compiled, and every name it imports
    from ``indi_nexus`` is resolved, so a renamed export fails here.
``PROSE``
    Not INDINexus code at all, or deliberately wrong code the page is warning
    against. Exempt, with the reason recorded next to it.

Every fence is compiled and has its imports resolved regardless of its claim,
because that costs nothing and a snippet that does not parse is never right.
"""

from __future__ import annotations

import ast
import importlib
import json
import math
import re
import sys
import textwrap
import urllib.parse
from dataclasses import dataclass
from typing import Any

import click
import pytest
import typer.main
from typer.testing import CliRunner

from indi_nexus.cli import app, load_device
from indi_nexus.driver import Device
from indi_nexus.exceptions import ProtocolError
from indi_nexus.protocol import IPState, ISState
from indi_nexus.settings import Settings
from indi_nexus.testing import DeviceHarness
from tests.docs_fences import REPO_ROOT, Fence, contains_snippet, fences, python_fences

#: Click needs a context to resolve a subcommand; nothing here uses its state.
_CONTEXT = click.Context(typer.main.get_command(app))

#: Every published page that carries code, plus the two repository front pages.
DOCUMENTED = [
    "README.md",
    "docs/index.md",
    "docs/getting-started.md",
    "docs/docker.md",
    "docs/guides/examples.md",
    "docs/guides/frontend.md",
    "docs/guides/porting-from-pyindi.md",
    "docs/guides/protocol.md",
    "docs/guides/tutorial-open-meteo.md",
    "docs/guides/writing-drivers.md",
]

RUNS = "runs"
EXCERPT = "excerpt"
COMPILES = "compiles"
PROSE = "prose"


@dataclass(frozen=True)
class Claim:
    """What the suite promises about one Python fence.

    Attributes
    ----------
    path : str
        The markdown file, relative to the repository root.
    match : str
        A distinctive substring identifying the fence. Keyed on the body rather
        than on an index so that inserting a fence above does not silently
        re-point every claim below it.
    how : str
        One of ``RUNS``, ``EXCERPT``, ``COMPILES`` or ``PROSE``.
    detail : str
        The source file for an ``EXCERPT``, the reason for a ``PROSE``, and the
        name of the test that runs it for a ``RUNS``.
    whole : bool
        When set, ``match`` is the fence's entire body rather than a substring
        of it. Needed for the one-line fences whose text also appears inside a
        longer one, where no substring can pick out which is meant.
    """

    path: str
    match: str
    how: str
    detail: str
    whole: bool = False

    def claims(self, fence: Fence) -> bool:
        """Return whether this claim is about one fence.

        Parameters
        ----------
        fence : Fence
            A block from the same page.

        Returns
        -------
        claimed : bool
            ``True`` when the fence is the one the claim names.
        """
        return self.match == fence.code.strip() if self.whole else self.match in fence.code


#: One entry per Python fence in :data:`DOCUMENTED`. Adding a fence to a page
#: without adding it here fails ``test_every_python_fence_is_accounted_for``.
CLAIMS = [
    # -- README.md ---------------------------------------------------------- #
    Claim("README.md", "class Mount(Device)", RUNS, "test_readme_mount_driver_runs"),
    Claim("README.md", "from my_driver import MyDriver", RUNS, "test_readme_harness_snippet_runs"),
    # -- docs/index.md ------------------------------------------------------ #
    Claim("docs/index.md", "MIN_BRIGHTNESS = 0", EXCERPT, "examples/flat_panel.py"),
    Claim(
        "docs/index.md", "async def test_lamp_turns_on", RUNS, "test_index_page_test_snippet_runs"
    ),
    # -- docs/guides/writing-drivers.md ------------------------------------- #
    Claim(
        "docs/guides/writing-drivers.md",
        "class FlatPanel(Device)",
        RUNS,
        "test_driver_guide_flat_panel_runs",
    ),
    Claim(
        "docs/guides/writing-drivers.md",
        'serial.Serial("/dev/ttyUSB0")',
        COMPILES,
        "needs pyserial and a real port; the point is where the calls go",
    ),
    Claim(
        "docs/guides/writing-drivers.md",
        'self.delete_property("CCD_COOLER"',
        RUNS,
        "test_driver_guide_connect_time_properties_run",
    ),
    Claim(
        "docs/guides/writing-drivers.md",
        "reading = self.read_hardware()",
        RUNS,
        "test_driver_guide_timer_snippet_runs",
    ),
    Claim(
        "docs/guides/writing-drivers.md",
        "if not math.isfinite(reading)",
        RUNS,
        "test_driver_guide_non_finite_reading_snippet_runs",
    ),
    Claim(
        "docs/guides/writing-drivers.md",
        "self._station.read_all()      # DON'T",
        PROSE,
        "the blocking call the page is warning against; running it is the bug",
    ),
    Claim(
        "docs/guides/writing-drivers.md",
        "self._station.read_all)     # DO",
        RUNS,
        "test_driver_guide_off_thread_snippet_runs",
    ),
    Claim(
        "docs/guides/writing-drivers.md",
        "Light.from_labels",
        RUNS,
        "test_driver_guide_lights_shortcut_runs",
    ),
    Claim(
        "docs/guides/writing-drivers.md",
        'emit="on_change")',
        COMPILES,
        "the element list is written as a literal ellipsis, so there is nothing to define",
    ),
    Claim(
        "docs/guides/writing-drivers.md",
        "run([Camera(), GuideChip(), FilterWheel()])",
        COMPILES,
        "three device classes the page never defines",
    ),
    Claim(
        "docs/guides/writing-drivers.md",
        "async def test_lamp_turns_on",
        RUNS,
        "test_driver_guide_test_snippet_runs",
    ),
    # -- docs/guides/tutorial-open-meteo.md --------------------------------- #
    *[
        Claim("docs/guides/tutorial-open-meteo.md", marker, EXCERPT, "examples/openmeteo_device.py")
        for marker in (
            "READINGS = [",
            "CONTEXT = [",
            '"WEATHER_PARAMETERS",                     #',
            "class OpenMeteoClient",
            "async def on_connect",
            "@every(minutes=5, when_connected=True)",
            "def _go_offline",
            "lights[element] = IPState.OK",
            '@on_new("GEOGRAPHIC_COORD")',
        )
    ],
    Claim(
        "docs/guides/tutorial-open-meteo.md",
        "payload = await self.off_thread(self._client.fetch, self._latitude, self._longitude)",
        EXCERPT,
        "examples/openmeteo_device.py",
        whole=True,
    ),
    Claim(
        "docs/guides/tutorial-open-meteo.md",
        "async def test_status_lights_flag_the_readings_that_are_out_of_range",
        EXCERPT,
        "tests/test_openmeteo_example.py",
    ),
    # -- docs/guides/porting-from-pyindi.md --------------------------------- #
    Claim(
        "docs/guides/porting-from-pyindi.md",
        "def ISGetProperties",
        PROSE,
        "libindi's C-shaped pyINDI API, shown for contrast; it is not INDINexus code",
    ),
    Claim(
        "docs/guides/porting-from-pyindi.md",
        '@on_new("commands")',
        RUNS,
        "test_porting_guide_indinexus_side_runs",
    ),
    # -- docs/guides/protocol.md -------------------------------------------- #
    Claim("docs/guides/protocol.md", "vector.selected()", RUNS, "test_protocol_guide_reads_run"),
]

#: The claims, indexed for lookup by the tests that execute a fence.
_BY_KEY = {(claim.path, claim.match): claim for claim in CLAIMS}


def snippet(path: str, match: str) -> str:
    """Return the body of one claimed fence, read from the markdown.

    Parameters
    ----------
    path : str
        The markdown file, relative to the repository root.
    match : str
        The claim's identifying substring.

    Returns
    -------
    code : str
        The fence body exactly as the page shows it.

    Raises
    ------
    AssertionError
        Raised if the substring does not identify exactly one fence, which is
        what a rewritten snippet looks like from here.
    """
    claim = _BY_KEY.get((path, match))
    assert claim is not None, f"{path}: {match!r} is not a declared claim"
    found = [f for f in python_fences(path) if claim.claims(f)]
    assert len(found) == 1, f"{path}: {match!r} matches {len(found)} fences, expected 1"
    return found[0].code


# --------------------------------------------------------------------------- #
# Coverage: no fence goes unexamined                                           #
# --------------------------------------------------------------------------- #
def test_every_python_fence_is_accounted_for() -> None:
    """Fail when a page gains a Python fence that no claim covers.

    This is the test that makes the rest of the module honest: it is what stops
    a new snippet from being documentation nobody checks.
    """
    unclaimed = []
    for path in DOCUMENTED:
        for fence in python_fences(path):
            hits = [c for c in CLAIMS if c.path == path and c.claims(fence)]
            if len(hits) != 1:
                unclaimed.append(f"{fence.where}: {len(hits)} claims match")
    assert not unclaimed, "add a Claim in tests/test_docs_snippets.py for:\n" + "\n".join(unclaimed)


def test_every_claim_still_finds_its_fence() -> None:
    """Fail when a claim points at a fence that has been rewritten or removed."""
    for claim in CLAIMS:
        found = [f for f in python_fences(claim.path) if claim.claims(f)]
        assert len(found) == 1, f"{claim.path}: {claim.match!r} matches {len(found)} fences"


def _all_python_fences() -> list[Fence]:
    """Return every Python fence on every documented page.

    Returns
    -------
    blocks : list of Fence
        In page order, then document order.
    """
    return [fence for path in DOCUMENTED for fence in python_fences(path)]


@pytest.mark.parametrize("fence", _all_python_fences(), ids=lambda f: f.where)
def test_python_fence_compiles(fence: Fence) -> None:
    """Compile one fence, allowing a bare ``await`` as a page legitimately shows.

    Parameters
    ----------
    fence : Fence
        The block under test.
    """
    compile(fence.code, fence.where, "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)


@pytest.mark.parametrize("fence", _all_python_fences(), ids=lambda f: f.where)
def test_python_fence_imports_resolve(fence: Fence) -> None:
    """Import every name a fence takes from ``indi_nexus``.

    A renamed or removed export fails here even in a snippet too partial to run.

    Parameters
    ----------
    fence : Fence
        The block under test.
    """
    for node in ast.walk(ast.parse(fence.code)):
        if not isinstance(node, ast.ImportFrom) or not (node.module or "").startswith("indi_nexus"):
            continue
        module = importlib.import_module(node.module or "")
        for alias in node.names:
            assert hasattr(module, alias.name), (
                f"{fence.where}: {node.module}.{alias.name} does not exist"
            )


@pytest.mark.parametrize(
    "claim",
    [c for c in CLAIMS if c.how == EXCERPT],
    ids=lambda c: f"{c.path}:{c.match[:32]}",
)
def test_excerpt_matches_its_source_file(claim: Claim) -> None:
    """Check a quoted excerpt against the file it quotes.

    Parameters
    ----------
    claim : Claim
        The excerpt claim, whose ``detail`` names the real file.
    """
    code = snippet(claim.path, claim.match)
    assert contains_snippet(code, claim.detail), (
        f"{claim.path}: this snippet is no longer in {claim.detail}:\n{code}"
    )


def test_the_excerpt_check_notices_a_changed_value() -> None:
    """Prove the excerpt comparison fails on drift rather than passing anything.

    A check that cannot fail is decoration, and this one's tolerance for trimmed
    arguments is exactly the kind of thing that quietly becomes total.
    """
    real = snippet("docs/guides/tutorial-open-meteo.md", "READINGS = [")
    assert contains_snippet(real, "examples/openmeteo_device.py")
    for damaged in (
        real.replace('"HUMIDITY"', '"DAMPNESS"'),  # a renamed element
        real.replace("90.0", "95.0"),  # a changed safe limit
        real.replace("cloud_cover", "cloudiness"),  # a renamed API field
    ):
        assert not contains_snippet(damaged, "examples/openmeteo_device.py")


def test_the_excerpt_check_notices_a_dropped_statement() -> None:
    """Prove an excerpt cannot claim a call the real file does not make."""
    code = snippet("docs/guides/tutorial-open-meteo.md", "async def on_connect")
    damaged = code.replace("self._publish(payload)", "self._publish(payload)\n    self.reboot()")
    assert contains_snippet(code, "examples/openmeteo_device.py")
    assert not contains_snippet(damaged, "examples/openmeteo_device.py")


# --------------------------------------------------------------------------- #
# Running the snippets                                                         #
# --------------------------------------------------------------------------- #
def execute(code: str, namespace: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a snippet and return the namespace it built.

    Parameters
    ----------
    code : str
        The fence body.
    namespace : dict or None, optional
        Names the surrounding page has already established for the reader.

    Returns
    -------
    namespace : dict
        The module namespace after execution.
    """
    scope: dict[str, Any] = {"__name__": "docs_snippet", **(namespace or {})}
    exec(compile(code, "<doc snippet>", "exec"), scope)  # noqa: S102 - that is the point
    return scope


def in_device(
    code: str,
    *,
    name: str = "Doc Device",
    context: dict[str, Any] | None = None,
    **attributes: Any,
) -> type[Device]:
    """Build a Device subclass whose body is a fragment lifted from a page.

    Several snippets are method definitions with no class around them, because
    the page has already established the class. This puts one back, verbatim and
    indented, so the fragment runs as the reader's would.

    Parameters
    ----------
    code : str
        The fence body: one or more method definitions.
    name : str, optional
        The INDI device name to give the class.
    context : dict or None, optional
        Module-level names the snippet reaches for, such as the instrument
        object a page tells the reader to supply.
    attributes : Any
        Extra class attributes, typically the stub hardware behind ``self._x``.

    Returns
    -------
    cls : type
        A ``Device`` subclass carrying the snippet's methods.
    """
    source = f"class _Snippet(Device):\n    name = {name!r}\n" + textwrap.indent(code, "    ")
    scope = execute(source, {"Device": Device, **_DRIVER_NAMES, **(context or {})})
    cls: type[Device] = scope["_Snippet"]
    for attribute, value in attributes.items():
        setattr(cls, attribute, value)
    return cls


def _split_on_blank_line(code: str) -> list[str]:
    """Split a fence into the paragraphs a blank line separates.

    Parameters
    ----------
    code : str
        The fence body.

    Returns
    -------
    parts : list of str
        Each run of non-blank lines, comments kept.
    """
    return [part for part in re.split(r"\n\s*\n", code.strip()) if part.strip()]


def evaluate_expressions(code: str, context: dict[str, Any]) -> list[Any]:
    """Evaluate a fence made of bare expressions and return their values.

    The expressions are left exactly as the page writes them; only the plumbing
    that captures each result is added.

    Parameters
    ----------
    code : str
        A fence whose statements are all expressions.
    context : dict
        The names the page has in scope at that point.

    Returns
    -------
    values : list
        One value per expression, in order.
    """
    tree = ast.parse(code)
    captured: list[Any] = []
    for index, statement in enumerate(tree.body):
        assert isinstance(statement, ast.Expr), f"line {index + 1} is not an expression"
    body = "\n".join(
        f"_captured.append({ast.get_source_segment(code, statement.value)})"  # type: ignore[attr-defined]
        for statement in tree.body
    )
    execute(body, {**context, "_captured": captured})
    return captured


def _driver_names() -> dict[str, Any]:
    """Return the driver and protocol names a page has in scope by that point.

    Returns
    -------
    names : dict
        Everything ``indi_nexus.driver`` and ``indi_nexus.protocol`` export,
        plus ``math``, which the guide tells the reader to import.
    """
    driver = importlib.import_module("indi_nexus.driver")
    protocol = importlib.import_module("indi_nexus.protocol")
    names = {n: getattr(m, n) for m in (protocol, driver) for n in m.__all__}
    return {**names, "math": math}


_DRIVER_NAMES = _driver_names()


async def test_readme_mount_driver_runs() -> None:
    """Run the README's mount driver, stubbing only what the README says you write.

    The README promises ``open_serial_link``, ``read_mount`` and ``slew_to`` are
    "the only parts you write", so supplying exactly those three and nothing
    else is the test of that sentence.
    """
    code = snippet("README.md", "class Mount(Device)")
    scope = execute(code, dict(_DRIVER_NAMES))
    slews: list[tuple[float, float]] = []

    class Stubbed(scope["Mount"]):  # type: ignore[misc, name-defined]
        """The README's Mount with its three hardware calls filled in."""

        async def open_serial_link(self) -> None:
            """Pretend the serial port opened."""

        async def read_mount(self) -> tuple[float, float]:
            """Return a fixed pointing."""
            return 5.59, -5.39

        async def slew_to(self, ra: float, dec: float) -> None:
            """Record the requested target."""
            slews.append((ra, dec))

    harness = DeviceHarness(Stubbed())
    await harness.setup()
    await harness.write("CONNECTION", CONNECT=True)
    await harness.tick("poll")

    assert harness.latest("EQUATORIAL_EOD_COORD").get("RA") == pytest.approx(5.59)
    assert harness.latest("EQUATORIAL_EOD_COORD").state is IPState.OK

    await harness.write("EQUATORIAL_EOD_COORD", RA=1.0, DEC=2.0)
    assert slews == [(1.0, 2.0)]


async def test_readme_harness_snippet_runs(tmp_path: Any) -> None:
    """Run the README's harness snippet against a driver ``indi-nexus new`` wrote.

    The snippet's comment says ``my_driver`` is "the file ``indi-nexus new``
    wrote", and it then asserts a ``TELEMETRY`` property and a ``poll`` job. So
    the scaffold really has to have both, which is what this checks.

    Parameters
    ----------
    tmp_path : Path
        pytest's per-test temporary directory, where the scaffold is written.
    """
    written = tmp_path / "my_driver.py"
    result = CliRunner().invoke(app, ["new", str(written), "--name", "MyDriver"])
    assert result.exit_code == 0, result.output
    sys.path.insert(0, str(tmp_path))
    try:
        code = snippet("README.md", "from my_driver import MyDriver")
        scope = execute("", {})
        exec(  # noqa: S102 - a top-level `await` needs a coroutine wrapper
            compile(
                "async def _snippet():\n" + textwrap.indent(code, "    "),
                "<doc snippet>",
                "exec",
            ),
            scope,
        )
        await scope["_snippet"]()
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("my_driver", None)


async def test_index_page_test_snippet_runs() -> None:
    """Run the front page's example test, exactly as written.

    It imports ``flat_panel``, so ``examples/`` goes on the path the way a
    reader's own directory would be.
    """
    code = snippet("docs/index.md", "async def test_lamp_turns_on")
    sys.path.insert(0, str(REPO_ROOT / "examples"))
    try:
        scope = execute(code)
        await scope["test_lamp_turns_on"]()
    finally:
        sys.path.remove(str(REPO_ROOT / "examples"))
        sys.modules.pop("flat_panel", None)


def _guide_flat_panel() -> type[Device]:
    """Return the driver guide's complete FlatPanel, built from the page.

    Returns
    -------
    cls : type
        The ``FlatPanel`` class the guide's first fence defines.
    """
    code = snippet("docs/guides/writing-drivers.md", "class FlatPanel(Device)")
    return execute(code, dict(_DRIVER_NAMES))["FlatPanel"]


async def test_driver_guide_flat_panel_runs() -> None:
    """Run the driver guide's complete driver and check every claim under it.

    The numbered notes below the fence promise an exclusive switch, a clamped
    brightness, a refusal while disconnected, and a lamp that goes out on
    disconnect. All four are asserted here, because a snippet that merely
    imports proves none of them.
    """
    harness = DeviceHarness(_guide_flat_panel()())
    await harness.setup()

    # (11) "Commands are refused while the link is down."
    await harness.write("LIGHT_CONTROL", ON=True)
    assert harness.latest("LIGHT_CONTROL").get("ON") is ISState.OFF

    await harness.write("CONNECTION", CONNECT=True)
    await harness.write("LIGHT_CONTROL", ON=True)
    # (13) "Turning one member on automatically turns the others off."
    assert harness.latest("LIGHT_CONTROL").get("ON") is ISState.ON
    assert harness.latest("LIGHT_CONTROL").get("OFF") is ISState.OFF
    assert "turned on" in harness.messages[-1]

    # (15) "hold the request to it rather than passing it straight through"
    await harness.write("LIGHT_BRIGHTNESS", BRIGHTNESS=9000.0)
    assert harness.latest("LIGHT_BRIGHTNESS").get("BRIGHTNESS") == pytest.approx(255.0)

    # (9) "a flat panel left lit fogs every exposure taken after the client went away"
    await harness.write("CONNECTION", DISCONNECT=True)
    assert harness.latest("LIGHT_CONTROL").get("OFF") is ISState.ON
    assert harness.latest("LIGHT_CONTROL").state is IPState.IDLE


async def test_driver_guide_test_snippet_runs() -> None:
    """Run the guide's own testing example, with the page's driver behind it.

    The snippet names ``FlatPanel`` and ``ISState`` without importing them,
    because the page introduced both further up. Handing it exactly those two
    is what a reader following the page top to bottom has.
    """
    code = snippet("docs/guides/writing-drivers.md", "async def test_lamp_turns_on")
    scope = execute(code, {"FlatPanel": _guide_flat_panel(), "ISState": ISState})
    await scope["test_lamp_turns_on"]()


async def test_driver_guide_connect_time_properties_run() -> None:
    """Run the define-on-connect / delete-on-disconnect pair from the guide.

    The prose promises the hook "is correct on the first disconnect and on every
    one after it", so the second disconnect is exercised too.
    """
    code = snippet("docs/guides/writing-drivers.md", 'self.delete_property("CCD_COOLER"')
    cls = in_device("async def setup(self) -> None:\n    self.define_connection()\n\n" + code)
    harness = DeviceHarness(cls())
    await harness.setup()

    await harness.write("CONNECTION", CONNECT=True)
    assert harness.latest("CCD_COOLER").get("TEMPERATURE") == pytest.approx(25.0)

    await harness.write("CONNECTION", DISCONNECT=True)
    assert [d.name for d in harness.deletes()] == ["CCD_COOLER"]

    # A second cycle: defining again, and deleting a name that is already gone.
    await harness.write("CONNECTION", CONNECT=True)
    await harness.write("CONNECTION", DISCONNECT=True)
    await harness.write("CONNECTION", DISCONNECT=True)
    assert [d.name for d in harness.deletes()] == ["CCD_COOLER"] * 2


async def test_driver_guide_timer_snippet_runs() -> None:
    """Run the guide's ``@every`` polling snippet.

    ``read_hardware`` is the reader's own, so it is stubbed and nothing else is.
    """
    code = snippet("docs/guides/writing-drivers.md", "reading = self.read_hardware()")
    setup = (
        "async def setup(self) -> None:\n"
        '    self.define_number("LIGHT_BRIGHTNESS", [Number(name="BRIGHTNESS")])\n\n'
    )
    cls = in_device(setup + code, read_hardware=lambda self: 42.0)
    harness = DeviceHarness(cls())
    await harness.setup()
    await harness.tick("poll")
    assert harness.latest("LIGHT_BRIGHTNESS").get("BRIGHTNESS") == pytest.approx(42.0)
    assert harness.latest("LIGHT_BRIGHTNESS").state is IPState.OK


async def test_driver_guide_non_finite_reading_snippet_runs() -> None:
    """Run the guide's non-finite-reading snippet on a good and a `nan` reading.

    The page's whole argument is that the property must stop claiming to be
    current without losing its last good value, so both halves are asserted.
    """
    code = snippet("docs/guides/writing-drivers.md", "if not math.isfinite(reading)")
    readings = [20.5, math.nan]

    class _Station:
        """A thermometer that reports one good value and then fails."""

        def read_temperature(self) -> float:
            """Return the next queued reading."""
            return readings.pop(0)

    setup = (
        "async def setup(self) -> None:\n"
        "    self.define_connection()\n"
        '    self.define_number("WEATHER_PARAMETERS", [Number(name="TEMPERATURE")])\n\n'
    )
    cls = in_device(setup + code, _station=_Station())
    harness = DeviceHarness(cls())
    await harness.setup()
    await harness.write("CONNECTION", CONNECT=True)

    await harness.tick("poll")
    assert harness.latest("WEATHER_PARAMETERS").get("TEMPERATURE") == pytest.approx(20.5)

    await harness.tick("poll")
    assert harness.latest("WEATHER_PARAMETERS").state is IPState.ALERT
    assert harness.latest("WEATHER_PARAMETERS").get("TEMPERATURE") == pytest.approx(20.5)


async def test_driver_guide_off_thread_snippet_runs() -> None:
    """Run the guide's ``off_thread`` polling snippet against a blocking read."""
    code = snippet("docs/guides/writing-drivers.md", "self._station.read_all)     # DO")

    class _Station:
        """A blocking instrument, standing in for a vendor library."""

        def read_all(self) -> dict[str, float]:
            """Return one reading per published element."""
            return {"TEMPERATURE": 11.5}

    setup = (
        "async def setup(self) -> None:\n"
        "    self.define_connection()\n"
        '    self.define_number("WEATHER_PARAMETERS", [Number(name="TEMPERATURE")])\n\n'
    )
    cls = in_device(setup + code, _station=_Station())
    harness = DeviceHarness(cls())
    await harness.setup()
    await harness.write("CONNECTION", CONNECT=True)
    await harness.tick("poll")
    assert harness.latest("WEATHER_PARAMETERS").get("TEMPERATURE") == pytest.approx(11.5)


async def test_driver_guide_lights_shortcut_runs() -> None:
    """Run the ``Light.from_labels`` / ``select`` shortcut and check its comments.

    The fence's comments make three claims - the names become ``idle``,
    ``opening`` and ``open``, the chosen light goes Busy, and the rest and the
    property go Idle - so all three are asserted.
    """
    code = snippet("docs/guides/writing-drivers.md", "Light.from_labels")
    define, select = (part for part in _split_on_blank_line(code))
    cls = in_device(f"async def setup(self) -> None:\n{textwrap.indent(define, '    ')}")
    device = cls()
    harness = DeviceHarness(device)
    await harness.setup()

    # "names become idle, opening, open; labels stay as written"
    defined = harness.latest("state_message")
    assert [e.name for e in defined.elements] == ["idle", "opening", "open"]
    assert [e.label for e in defined.elements] == ["Idle", "Opening", "Open"]

    scope = execute(f"def _do(self):\n{textwrap.indent(select, '    ')}", dict(_DRIVER_NAMES))
    scope["_do"](device)

    latest = harness.latest("state_message")
    assert latest.get("opening") is IPState.BUSY
    assert latest.get("idle") is IPState.IDLE
    assert latest.get("open") is IPState.IDLE
    assert latest.state is IPState.BUSY


async def test_porting_guide_indinexus_side_runs() -> None:
    """Run the porting guide's INDINexus column, hardware failure included.

    The fence is the answer to the pyINDI fragment above it, so the behaviour it
    claims - an ``AT_MOST_ONE`` switch, a failed command reported and rolled
    back - is what makes the port correct rather than merely compiling.
    """
    code = snippet("docs/guides/porting-from-pyindi.md", '@on_new("commands")')

    class _Hardware:
        """A shutter that opens and refuses to close."""

        def open(self) -> bool:
            """Succeed."""
            return True

        def close(self) -> bool:
            """Fail, the way a jammed shutter does."""
            return False

    # The fence reaches a module-level `hardware`, which the page's prose implies
    # is the reader's own instrument object.
    cls = in_device(code, name="Commands", context={"hardware": _Hardware()})
    harness = DeviceHarness(cls())
    await harness.setup()

    await harness.write("commands", open=True)
    assert harness.latest("commands").get("open") is ISState.ON
    assert harness.latest("commands").state is IPState.BUSY

    await harness.write("commands", close=True)
    assert harness.latest("commands").get("close") is ISState.OFF
    assert harness.latest("commands").state is IPState.ALERT
    assert "Failed to close" in harness.messages[-1]


async def test_protocol_guide_reads_run() -> None:
    """Run the protocol page's two reader calls against a real client write.

    The page's point is that a ``new`` names only what the client changed, so
    the vector handed in here carries one element of a two-element property.
    """
    code = snippet("docs/guides/protocol.md", "vector.selected()")
    seen: list[Any] = []
    cls = in_device(
        'async def setup(self) -> None:\n    self.define_switch("S", '
        '[Switch(name="a"), Switch(name="b")], rule=ISRule.AT_MOST_ONE)\n\n'
        '@on_new("S")\n'
        "async def _handle(self, vector) -> None:\n"
        "    seen.append(vector)\n",
        context={"seen": seen},
    )
    harness = DeviceHarness(cls())
    await harness.setup()
    await harness.write("S", a=True)

    selected, got = evaluate_expressions(
        code, {"vector": seen[0], "name": "b", "default": ISState.OFF}
    )
    assert selected == "a"
    # "a client that changes only one element sends only that one"
    assert got is ISState.OFF


# --------------------------------------------------------------------------- #
# Shell fences: the commands the pages tell people to type                     #
# --------------------------------------------------------------------------- #
def _shell_commands(path: str) -> list[str]:
    r"""Return every shell command in a page's ``bash`` fences, joined at ``\``.

    Parameters
    ----------
    path : str
        The markdown file, relative to the repository root.

    Returns
    -------
    commands : list of str
        One entry per command, comments and blank lines dropped.
    """
    commands: list[str] = []
    for fence in fences(path):
        if fence.lang != "bash":
            continue
        joined = fence.code.replace("\\\n", " ")
        for line in joined.splitlines():
            # A trailing `# ...` on these pages is a note to the reader, not part
            # of the command.
            stripped = line.split("#")[0].strip()
            if stripped:
                commands.append(stripped)
    return commands


@pytest.mark.parametrize("path", [*DOCUMENTED, "DEVELOPMENT.md"])
def test_documented_cli_commands_exist(path: str) -> None:
    """Check every ``indi-nexus`` command and flag a page shows against the CLI.

    A page telling someone to pass a flag the CLI does not have is exactly the
    kind of drift a rename leaves behind, and nothing else in the suite reads
    these fences.

    Parameters
    ----------
    path : str
        The markdown file under test.
    """
    group = typer.main.get_command(app)
    checked = 0
    for command in _shell_commands(path):
        words = command.split()
        if words[0] != "indi-nexus":
            continue
        checked += 1
        rest = [w for w in words[1:] if not w.startswith("-")]
        flags = [w.split("=")[0] for w in words[1:] if w.startswith("--")]
        parameters = list(group.params)
        if rest:
            subcommand = group.get_command(_CONTEXT, rest[0])
            assert subcommand is not None, f"{path}: `indi-nexus {rest[0]}` is not a command"
            parameters += list(subcommand.params)
        # `--help` is click's, on every command, and appears in no parameter list.
        known = {"--help", *(option for parameter in parameters for option in parameter.opts)}
        for flag in flags:
            assert flag in known, f"{path}: `{command}` uses {flag}, which the CLI has not got"
    if path in {"docs/index.md", "docs/getting-started.md", "README.md", "DEVELOPMENT.md"}:
        assert checked, f"{path} stopped showing any indi-nexus command"


@pytest.mark.parametrize("path", [*DOCUMENTED, "DEVELOPMENT.md"])
def test_documented_example_drivers_are_importable(path: str) -> None:
    """Check every ``examples.module:Class`` a page names actually resolves.

    Parameters
    ----------
    path : str
        The markdown file under test.
    """
    text = (REPO_ROOT / path).read_text()
    for spec in set(re.findall(r"\bexamples\.[a-z_]+:[A-Za-z_]+", text)):
        assert issubclass(load_device(spec), Device), f"{path}: {spec} is not a Device"


def test_docker_page_environment_variables_exist() -> None:
    """Check the variables ``docs/docker.md`` shows are read by something.

    Each is either resolved by ``docker/entrypoint.sh`` or a field of
    :class:`~indi_nexus.settings.Settings`. A page advertising a variable
    nothing reads is a silently ignored instruction, which is worse than none.
    """
    entrypoint = (REPO_ROOT / "docker" / "entrypoint.sh").read_text()
    known = set(Settings.model_fields)
    shown = set()
    for fence in fences("docs/docker.md"):
        if fence.lang == "bash":
            shown.update(re.findall(r"-e (\w+)=", fence.code))
    assert shown, "docs/docker.md stopped showing any -e VARIABLE"
    for variable in sorted(shown):
        field = variable.removeprefix("INDI_NEXUS_").lower()
        assert variable in entrypoint or field in known, (
            f"docs/docker.md advertises {variable}, which nothing reads"
        )


async def test_writing_drivers_guide_quotes_the_real_error_message() -> None:
    """Check the guide's quoted ``ProtocolError`` against the one the code raises.

    The page shows a reader the exact line they will see, which makes it a claim
    about a format string in ``driver/property.py`` that nothing else reads.
    """
    quoted = next(
        f.code.strip()
        for f in fences("docs/guides/writing-drivers.md")
        if f.lang == "" and "ProtocolError" in f.code
    )
    device, prop, element = quoted.split(" ")[1].split(".")

    cls = in_device(
        f"async def setup(self) -> None:\n"
        f"    self.define_number({prop!r}, [Number(name={element!r})])\n",
        name=device,
    )
    instance = cls()
    harness = DeviceHarness(instance)
    await harness.setup()

    with pytest.raises(ProtocolError) as raised:
        instance[prop].set(**{element: math.nan})
    assert f"ProtocolError: {raised.value}" == quoted


# --------------------------------------------------------------------------- #
# The tutorial's non-Python fences, which are claims about the API it calls    #
# --------------------------------------------------------------------------- #
def test_tutorial_request_matches_what_the_driver_asks_for() -> None:
    """Check the tutorial's example request URL against the query the driver builds.

    The page opens by saying "ask for a short list", and then the driver's
    correctness depends on that list. No network is used: the request is
    intercepted at ``urlopen``.
    """
    from examples import openmeteo_device

    shown = next(f for f in fences("docs/guides/tutorial-open-meteo.md") if f.lang == "")
    documented = urllib.parse.parse_qs(urllib.parse.urlsplit("".join(shown.code.split())).query)

    captured: dict[str, str] = {}

    def _capture(url: str, **_: Any) -> None:
        captured["url"] = url
        raise OSError("no network in tests")

    original = openmeteo_device.urllib.request.urlopen
    openmeteo_device.urllib.request.urlopen = _capture  # type: ignore[assignment]
    try:
        with pytest.raises(OSError, match="no network"):
            openmeteo_device.OpenMeteoClient().fetch(34.0522, -118.2437)
    finally:
        openmeteo_device.urllib.request.urlopen = original  # type: ignore[assignment]

    actual = urllib.parse.parse_qs(urllib.parse.urlsplit(captured["url"]).query)
    assert captured["url"].startswith(shown.code.strip().splitlines()[0].strip())
    for field in ("current", "daily"):
        assert set(documented[field][0].split(",")) == set(actual[field][0].split(",")), (
            f"the tutorial's {field}= list is not what OpenMeteoClient.fetch asks for"
        )
    assert documented["forecast_days"] == actual["forecast_days"]
    assert documented["timezone"] == actual["timezone"]


def test_tutorial_reply_fields_are_in_the_recorded_response() -> None:
    """Check the tutorial's quoted reply against the recorded real one.

    The page prints "the reply's interesting parts", which is a claim about
    field names the service really sends. ``tests/data/open_meteo_response.json``
    is a recording of an actual reply, so it settles the claim without a socket.
    """
    quoted = next(f for f in fences("docs/guides/tutorial-open-meteo.md") if f.lang == "json")
    shown = json.loads(quoted.code)
    recorded = json.loads((REPO_ROOT / "tests/data/open_meteo_response.json").read_text())
    for block, fields in shown.items():
        assert block in recorded, f"the tutorial quotes a `{block}` block the API does not send"
        missing = sorted(set(fields) - set(recorded[block]))
        assert not missing, f"the tutorial quotes {block} fields the API does not send: {missing}"


def test_tutorial_quoted_reply_covers_every_judged_reading() -> None:
    """Check the quoted reply still shows a value for each reading the driver judges.

    The page introduces the reply as what shapes the driver, so a reading added
    to ``READINGS`` with no line in the quotation leaves the tutorial explaining
    a driver it no longer shows the input for.
    """
    from examples.openmeteo_device import READINGS

    quoted = next(f for f in fences("docs/guides/tutorial-open-meteo.md") if f.lang == "json")
    current = json.loads(quoted.code)["current"]
    missing = sorted({field for field, *_rest in READINGS} - set(current))
    assert not missing, f"the tutorial's quoted reply is missing {missing}"
