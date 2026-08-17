"""Read the documentation's code fences, and compare one against real source.

The documentation is full of Python that a reader will paste, and nothing in the
build used to run any of it. This module is the shared half of closing that: it
pulls the fences straight out of the markdown at test time - never from a
hand-kept copy, which only drifts more quietly - and offers the one comparison
the extracted snippets need.

``fences`` is the reader. ``contains_snippet`` is the comparison: a documentation
snippet is nearly always a **trimmed excerpt** of a real file, so an equality
check is useless and a substring check is meaningless. It asks the question the
excerpt actually makes: *is every statement here, with every argument it shows,
present in that order in the real file?* Formatting, comments, docstrings, type
annotations and arguments the page left out are all free to differ; a renamed
element, a changed literal or a dropped call is not.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The repository root, two directories up from this file.
REPO_ROOT = Path(__file__).resolve().parent.parent

#: An opening fence line: optional indent, three or more backticks, an info string.
_FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<ticks>`{3,})(?P<info>.*)$")


@dataclass(frozen=True)
class Fence:
    """One fenced code block, as it appears in a markdown file.

    Attributes
    ----------
    path : str
        The file's path relative to the repository root.
    line : int
        The 1-based line number of the opening fence.
    lang : str
        The first word of the info string, lowercased; ``""`` when absent.
    code : str
        The block's body, dedented to the fence's own indent.
    """

    path: str
    line: int
    lang: str
    code: str

    @property
    def where(self) -> str:
        """Return a ``path:line`` locator for an assertion message."""
        return f"{self.path}:{self.line}"


def fences(relative_path: str) -> list[Fence]:
    """Return every fenced code block in one markdown file.

    Parameters
    ----------
    relative_path : str
        Path to the markdown file, relative to the repository root.

    Returns
    -------
    blocks : list of Fence
        Every block, in document order.
    """
    text = (REPO_ROOT / relative_path).read_text()
    blocks: list[Fence] = []
    opening: Fence | None = None
    ticks = ""
    indent = ""
    body: list[str] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        match = _FENCE_RE.match(raw)
        if opening is None:
            if match is None:
                continue
            ticks, indent = match["ticks"], match["indent"]
            info = match["info"].strip()
            opening = Fence(relative_path, number, info.split(" ")[0].lower(), "")
            body = []
            continue
        # A closing fence is the same run of backticks with nothing after it.
        if match is not None and match["ticks"].startswith(ticks) and not match["info"].strip():
            blocks.append(Fence(opening.path, opening.line, opening.lang, "\n".join(body)))
            opening = None
            continue
        body.append(raw.removeprefix(indent))
    if opening is not None:  # pragma: no cover - a malformed page would fail elsewhere
        raise AssertionError(f"unclosed code fence at {opening.where}")
    return blocks


def python_fences(relative_path: str) -> list[Fence]:
    """Return only the Python fences of one markdown file.

    Parameters
    ----------
    relative_path : str
        Path to the markdown file, relative to the repository root.

    Returns
    -------
    blocks : list of Fence
        Every fence whose info string starts with ``python`` or ``py``.
    """
    return [f for f in fences(relative_path) if f.lang in {"python", "py"}]


# --------------------------------------------------------------------------- #
# Comparing an excerpt against the file it was excerpted from                  #
# --------------------------------------------------------------------------- #
#: Fields that say where a node sat in its own file, never what it says.
_POSITION_FIELDS = frozenset({"lineno", "col_offset", "end_lineno", "end_col_offset", "ctx"})


def _is_gap(node: ast.AST) -> bool:
    """Return whether a node is a bare ``...``, the excerpt's "and so on" marker.

    Parameters
    ----------
    node : ast.AST
        Any node from the excerpt.

    Returns
    -------
    gap : bool
        ``True`` for an expression statement whose value is ``Ellipsis``.
    """
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and node.value.value is Ellipsis
    )


def _is_docstring(node: ast.AST) -> bool:
    """Return whether a statement is a bare string, i.e. a docstring.

    Parameters
    ----------
    node : ast.AST
        Any statement.

    Returns
    -------
    docstring : bool
        ``True`` for an expression statement holding a string constant.
    """
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """Return a statement list without its leading docstring.

    Docstrings are prose. A page that shortens one, or drops the parameter
    section, has not changed the code, so comparing them would only generate
    churn and teach people to route around the check.

    Parameters
    ----------
    body : list of ast.stmt
        A module, class or function body, from either side of the comparison.

    Returns
    -------
    body : list of ast.stmt
        The same list, minus a leading string-constant expression.
    """
    return body[1:] if body and _is_docstring(body[0]) else body


def _statements_match(excerpt: list[ast.stmt], source: list[ast.stmt]) -> bool:
    """Return whether an excerpt's statements appear in order inside a body.

    A bare ``...`` in the excerpt skips any number of statements, which is how
    the documentation writes "and the rest of this function".

    Parameters
    ----------
    excerpt : list of ast.stmt
        The statements the documentation shows.
    source : list of ast.stmt
        The statements the real file has, docstring already removed.

    Returns
    -------
    matched : bool
        ``True`` if every excerpt statement was matched, in order.
    """
    excerpt, source = _strip_docstring(excerpt), _strip_docstring(source)
    if not excerpt:
        return True
    if _is_gap(excerpt[0]):
        # A gap absorbs zero or more statements; try every resumption point.
        return any(_statements_match(excerpt[1:], source[i:]) for i in range(len(source) + 1))
    for start in range(len(source)):
        if _nodes_match(excerpt[0], source[start]) and _statements_match(
            excerpt[1:], source[start + 1 :]
        ):
            return True
    return False


def _normalise(node: ast.AST) -> ast.AST:
    """Return a node with the differences a trimmed excerpt is allowed to have.

    An annotated assignment in the source is written unannotated on the page
    often enough that keeping the two apart would only teach people to annotate
    for the test's benefit.

    Parameters
    ----------
    node : ast.AST
        Any node.

    Returns
    -------
    node : ast.AST
        The node, or an equivalent plain assignment for an ``AnnAssign``.
    """
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        return ast.Assign(targets=[node.target], value=node.value)
    return node


def _nodes_match(excerpt: ast.AST, source: ast.AST) -> bool:
    """Return whether one excerpt node is satisfied by one source node.

    Every field the excerpt carries has to match. Statement bodies and call
    arguments are matched as *subsequences*, so a page that drops ``label=`` or
    elides the rest of a function still matches - but every argument it does
    show has to be the one the file has.

    Parameters
    ----------
    excerpt : ast.AST
        A node from the documentation snippet.
    source : ast.AST
        The candidate node from the real file.

    Returns
    -------
    matched : bool
        ``True`` when the source node satisfies the excerpt node.
    """
    if _is_gap(excerpt):
        return True
    excerpt, source = _normalise(excerpt), _normalise(source)
    if type(excerpt) is not type(source):
        return False
    for field in excerpt._fields:
        if field in _POSITION_FIELDS:
            continue
        left, right = getattr(excerpt, field, None), getattr(source, field, None)
        # A page routinely drops the type annotations, so an absent one asks
        # nothing of the file rather than insisting the file has none either.
        if field in {"returns", "annotation"} and left is None:
            continue
        if field in {"body", "orelse", "finalbody"} and isinstance(left, list):
            if not _statements_match(list(left), list(right or [])):
                return False
        elif field in {"args", "keywords", "decorator_list"} and isinstance(left, list):
            if not _subsequence(list(left), list(right or [])):
                return False
        elif not _values_match(left, right):
            return False
    return True


def _subsequence(excerpt: list[Any], source: list[Any]) -> bool:
    """Return whether every excerpt item appears in order among the source items.

    Parameters
    ----------
    excerpt : list
        Arguments, keywords or decorators the page shows.
    source : list
        The full list from the real file.

    Returns
    -------
    matched : bool
        ``True`` when all of them were found, in order.
    """
    remaining = list(source)
    for item in excerpt:
        for index, candidate in enumerate(remaining):
            if _values_match(item, candidate):
                remaining = remaining[index + 1 :]
                break
        else:
            return False
    return True


def _values_match(left: Any, right: Any) -> bool:
    """Return whether two AST field values are equivalent.

    Parameters
    ----------
    left : object
        The excerpt's value: a node, a list of nodes, or a plain scalar.
    right : object
        The source's value.

    Returns
    -------
    matched : bool
        ``True`` when they say the same thing.
    """
    if isinstance(left, ast.AST) and isinstance(right, ast.AST):
        return _nodes_match(left, right)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _values_match(a, b) for a, b in zip(left, right, strict=True)
        )
    return bool(left == right)


def contains_snippet(snippet: str, source_path: str) -> bool:
    """Return whether a documentation snippet is a trimmed excerpt of a file.

    Parameters
    ----------
    snippet : str
        The fence body, as the page shows it.
    source_path : str
        Path to the real file, relative to the repository root.

    Returns
    -------
    matched : bool
        ``True`` when every statement in the snippet, at any nesting depth,
        is present in the file in the order the snippet gives.
    """
    module = ast.parse((REPO_ROOT / source_path).read_text())
    # Any statement list in the file is a candidate, not only the top level: a
    # page quotes the inside of a method, of a loop, or of one arm of an `if`.
    blocks: list[list[ast.stmt]] = []
    for node in ast.walk(module):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                blocks.append(block)
    # A top-level `...` can elide a change of scope as well as a run of
    # statements - "this line, from inside the loop; then these, after it" - so
    # each run between gaps is matched on its own. Order still binds inside a run.
    return all(
        any(_statements_match(segment, block) for block in blocks)
        for segment in _segments(ast.parse(snippet).body)
    )


def _segments(excerpt: list[ast.stmt]) -> list[list[ast.stmt]]:
    """Split an excerpt into the runs of statements separated by a bare ``...``.

    Parameters
    ----------
    excerpt : list of ast.stmt
        The snippet's top-level statements.

    Returns
    -------
    segments : list of list of ast.stmt
        The non-empty runs, in order.
    """
    segments: list[list[ast.stmt]] = [[]]
    for statement in excerpt:
        if _is_gap(statement):
            segments.append([])
        else:
            segments[-1].append(statement)
    return [run for run in segments if run]
