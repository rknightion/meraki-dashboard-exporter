"""Tests for correct exception handling syntax across the codebase.

Note on Python 3.14 behavior:
In Python 3.14, `except TypeError, ValueError:` is valid syntax equivalent to
`except (TypeError, ValueError):` — both forms produce the same AST (an ExceptHandler
with a Tuple type node). This differs from Python 3.11 and earlier where the
comma syntax is a SyntaxError.

Ruff 0.15.9 with target-version=py314 formats `except (TypeError, ValueError):` to
`except TypeError, ValueError:` — this is the intentional ruff style for Python 3.14+.

These tests verify the AST semantics: each ExceptHandler with multiple exception types
must use a Tuple (catching all listed types), not a bare Name (catching only one type
and potentially binding another as the exception variable).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

KNOWN_EXCEPTION_FILES = [
    "src/meraki_dashboard_exporter/core/error_handling.py",
    "src/meraki_dashboard_exporter/api/client.py",
    "src/meraki_dashboard_exporter/core/api_helpers.py",
    "src/meraki_dashboard_exporter/core/collector.py",
]


@pytest.mark.parametrize("filepath", KNOWN_EXCEPTION_FILES)
def test_no_python2_except_syntax(filepath: str) -> None:
    """Verify no except clauses accidentally use 'except X as Y' with exception type names.

    The dangerous Python 2 pattern is: `except SomeError, e:` which in Python 3 becomes
    `except SomeError as e:` — catching only SomeError and binding it to 'e'.

    In Python 3.14, `except X, Y:` (without parentheses, where Y is NOT a variable name
    but a known exception type) is parsed as a Tuple — catching both X and Y.

    This test catches the truly dangerous case: ExceptHandler where name matches
    a known exception type name AND type is a single Name node (not a Tuple).
    That would mean only the first exception is caught and the second is silently
    used as the variable name.
    """
    source = Path(filepath).read_text(encoding="utf-8")
    tree = ast.parse(source)

    builtin_exceptions = {
        "Exception",
        "BaseException",
        "ValueError",
        "TypeError",
        "AttributeError",
        "ImportError",
        "RuntimeError",
        "KeyError",
        "IndexError",
        "OSError",
        "IOError",
        "NotImplementedError",
        "StopIteration",
        "GeneratorExit",
        "SystemExit",
        "KeyboardInterrupt",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            # The dangerous case: `except SomeError as ValueError:` pattern
            # where name is a known exception type (not a variable name)
            if (
                node.name is not None
                and node.name in builtin_exceptions
                and node.type is not None
                and isinstance(node.type, ast.Name)
            ):
                pytest.fail(
                    f"{filepath}:{node.lineno} - except {node.type.id} as {node.name}: "
                    f"binds exception to a builtin exception name '{node.name}'. "
                    f"This indicates a Python 2 comma syntax that was mis-parsed. "
                    f"Use 'except ({node.type.id}, {node.name}):' to catch both types."
                )
