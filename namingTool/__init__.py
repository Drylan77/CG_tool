"""namingTool - VFX modeling naming convention tool for Maya 2025.3.

Public entry point::

    import namingTool
    namingTool.show()

Headless (no UI), e.g. from a publish script::

    from namingTool.core import checks
    report = checks.run_all(scope="scene")
"""

from __future__ import annotations

__version__ = "1.0.0"


def show(*args, **kwargs):
    """Open the dockable Naming Tool window (imports PySide6 lazily)."""
    from .launch import main
    return main(*args, **kwargs)
