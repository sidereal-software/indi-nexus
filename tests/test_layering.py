"""Tests for the package's import layering.

Two properties that are cheap to keep and expensive to notice the loss of: the
module import graph has no cycles, and :mod:`indi_nexus.web` - the
browser-facing edge - imports only downwards, towards the client and the
protocol, never back into the driver SDK.

The graph is read out of the source with :mod:`ast` rather than by importing,
because an import-time check can only see the modules that happen to have been
loaded. Two kinds of import are excluded deliberately: one guarded by
``TYPE_CHECKING`` is erased before the interpreter ever runs it, and one inside
a function body runs long after every module is loaded, which is exactly how
:meth:`indi_nexus.driver.device.Device.run` reaches the runtime without the two
modules importing each other.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "indi_nexus"


def _module_name(path: Path) -> str:
    """Return the dotted module name a source file is imported under.

    Parameters
    ----------
    path : Path
        A ``.py`` file inside the package.

    Returns
    -------
    name : str
        The dotted name, with a package's ``__init__`` reported as the package.
    """
    parts = list(path.relative_to(_PACKAGE.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _import_graph() -> dict[str, set[str]]:
    """Build the module-level intra-package import graph.

    Returns
    -------
    graph : dict
        Module name -> the ``indi_nexus`` modules it imports at module level.
    """
    graph: dict[str, set[str]] = {}
    for path in sorted(_PACKAGE.rglob("*.py")):
        name = _module_name(path)
        deps: set[str] = set()
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                if node.module.startswith("indi_nexus"):
                    deps.add(node.module)
            elif isinstance(node, ast.Import):
                deps |= {a.name for a in node.names if a.name.startswith("indi_nexus")}
        graph[name] = deps - {name}
    return graph


def _reachable(graph: dict[str, set[str]], start: str) -> set[str]:
    """Return every module reachable from ``start``, itself included.

    Parameters
    ----------
    graph : dict
        The import graph from :func:`_import_graph`.
    start : str
        The module to start from.

    Returns
    -------
    modules : set of str
        The transitive closure of ``start``'s imports.
    """
    seen = {start}
    stack = [start]
    while stack:
        for dep in graph.get(stack.pop(), ()):
            if dep in graph and dep not in seen:
                seen.add(dep)
                stack.append(dep)
    return seen


def test_the_import_graph_is_acyclic():
    """No module-level import cycle anywhere in the package.

    A cycle here is not a style complaint: it makes import order load-bearing,
    so which of two modules a caller reaches for first decides whether the
    package imports at all.
    """
    graph = _import_graph()
    state: dict[str, int] = {}
    cycles: list[list[str]] = []

    def visit(module: str, stack: list[str]) -> None:
        """Depth-first walk recording any back edge as a cycle."""
        state[module] = 1
        for dep in sorted(graph[module]):
            if dep not in graph:
                continue
            if state.get(dep) == 1:
                cycles.append(stack[stack.index(dep) :] + [dep])
            elif state.get(dep, 0) == 0:
                visit(dep, [*stack, dep])
        state[module] = 2

    for module in sorted(graph):
        if state.get(module, 0) == 0:
            visit(module, [module])

    assert not cycles, f"import cycles: {cycles}"


def test_the_web_package_does_not_import_the_driver_sdk():
    """``indi_nexus.web`` is a client of ``indiserver``, not a driver host.

    The web layer sits above the client, which sits above the protocol. The one
    thing that used to break that - the in-process hub, now
    :mod:`indi_nexus.hub` - is a driver harness that never belonged behind the
    browser-facing package. Importing the bridge should not cost the SDK.
    """
    graph = _import_graph()
    reached = _reachable(graph, "indi_nexus.web")
    assert not {m for m in reached if m.startswith("indi_nexus.driver") or m == "indi_nexus.hub"}


def test_importing_the_web_package_loads_no_driver_module():
    """The static rule above holds for a real interpreter too.

    Run in a subprocess because this one has already imported half the package
    for other tests, so its ``sys.modules`` proves nothing.
    """
    code = (
        "import sys, indi_nexus.web; "
        "print([m for m in sys.modules if m.startswith('indi_nexus.driver')])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"
