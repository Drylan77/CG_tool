"""Entry point and dockable workspaceControl management for the Naming Tool.

Usage from Maya (Script Editor / shelf)::

    import namingTool
    namingTool.show()
"""

from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("namingTool")

WORKSPACE_CONTROL = "namingToolWorkspaceControl"
_window = None


def _delete_existing() -> None:
    import maya.cmds as cmds  # type: ignore
    for name in (WORKSPACE_CONTROL, WORKSPACE_CONTROL + "WorkspaceControl"):
        if cmds.workspaceControl(name, exists=True):
            cmds.deleteUI(name, control=True)


def main(config_path: str = None):
    """Create (or re-show) the Naming Tool as a dockable Maya window."""
    global _window
    from .ui.main_window import NamingToolWindow

    try:
        _delete_existing()
    except Exception:  # noqa: BLE001 - not fatal if the control was already gone
        log.debug("no existing workspace control to delete")

    _window = NamingToolWindow(config_path=config_path)
    _window.show_dockable()
    return _window


if __name__ == "__main__":
    main()
