"""End to end: a browser driving a real C++ driver through the whole stack.

Chrome to the panel, panel to the bridge over a WebSocket, bridge to our client,
client to a real ``indiserver``, and ``indiserver`` to a real C++ simulator. This is
the only test that puts the hand-authored TypeScript wire types in front of property
shapes nobody on this project wrote: everything else checks them against JSON our own
Pydantic models produced, which cannot disagree.

Skipped when Playwright is not installed, so the rest of the interop suite still
runs without a browser.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from dataclasses import dataclass

import pytest
from conftest import REPO_ROOT, Server, free_port

playwright_api = pytest.importorskip(
    "playwright.sync_api",
    reason="playwright missing: pip install -e '.[interop]' && playwright install chromium",
)

DEVICE = "Telescope Simulator"


@dataclass
class Panel:
    """A running panel and the hub it is pointed at."""

    url: str
    hub: Server


@pytest.fixture
def panel(indi_server):
    """Serve the panel against a real hub running a real C++ driver.

    Yields
    ------
    panel : Panel
        The panel's URL and the hub behind it, so a test can take the hub away.
    """
    hub = indi_server("indi_simulator_telescope")
    port = free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "indikit.cli",
            "serve",
            "--port",
            str(port),
            "--indi-port",
            str(hub.port),
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.25):
                break
        except OSError:
            if process.poll() is not None:
                pytest.fail("indikit serve exited during startup")
            time.sleep(0.2)
    else:  # pragma: no cover - only when the bridge never binds
        process.terminate()
        pytest.fail("indikit serve never listened")

    yield Panel(url=f"http://127.0.0.1:{port}", hub=hub)

    process.terminate()
    process.wait(timeout=10)


def test_panel_drives_a_real_cpp_driver(panel):
    """Clicking Connect in the browser connects the real C++ simulator.

    The assertion is that the control ends up *checked*, not merely that the click
    landed. A switch only reads back as on once the driver has confirmed it, so this
    passing means the write travelled browser to bridge to indiserver to the C++
    driver, and its confirmation came all the way back.
    """
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        try:
            page.goto(panel.url, wait_until="networkidle")
            page.wait_for_selector(f"text={DEVICE}", timeout=30_000)

            # A switch vector renders as a fieldset of toggle buttons, so the members
            # are buttons carrying `aria-pressed` - not radios carrying `aria-checked`.
            # That is deliberate and is the assertion, not an implementation detail:
            # the ARIA radio pattern is selection-follows-focus, so arrowing from
            # Disconnect to Connect would tell a screen reader the selection had moved
            # while nothing had gone on the wire. See `web/CLAUDE.md`. If this ever
            # reads `radio` again, the panel has regressed rather than the test.
            connect = page.get_by_role("button", name="Connect", exact=True).first
            connect.wait_for(timeout=30_000)
            assert connect.get_attribute("aria-pressed") == "false", (
                "the simulator should start disconnected"
            )

            connect.click()

            page.wait_for_function(
                """() => {
                    const el = [...document.querySelectorAll('[aria-pressed]')]
                        .find((e) => e.textContent.trim() === 'Connect');
                    return el && el.getAttribute('aria-pressed') === 'true';
                }""",
                timeout=30_000,
            )
        finally:
            browser.close()


def test_panel_stays_up_when_the_hub_dies(panel):
    """The page keeps its content and reports the upstream as down.

    An operator will meet this: `indiserver` restarts, or the observatory network
    blips. A panel that goes blank is worse than one that says so.
    """
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        try:
            page.goto(panel.url, wait_until="networkidle")
            page.wait_for_selector(f"text={DEVICE}", timeout=30_000)

            panel.hub.stop()

            # The page is still a page: the device it already knew about stays on
            # screen rather than the whole view collapsing.
            page.wait_for_timeout(3_000)
            assert page.is_visible(f"text={DEVICE}"), "the panel emptied when the hub died"
            # And the connection indicator is still rendered, so an operator has
            # something to read rather than a frozen screen.
            assert page.is_visible("text=indiserver")
        finally:
            browser.close()
