"""Drag-and-drop installer for the Naming Tool (Maya 2025.3).

Drag this file from a file browser into a running Maya viewport. Maya runs
``onMayaDroppedPythonFile`` which:
    1. adds this repo to Maya's Python path (persisted in userSetup.py),
    2. creates a shelf button that opens the tool,
    3. opens the tool.
"""

from __future__ import annotations

import os

TOOL_ROOT = os.path.dirname(os.path.abspath(__file__))  # contains namingTool/

BUTTON_COMMAND = (
    "import sys\n"
    "root = r'{root}'\n"
    "if root not in sys.path:\n"
    "    sys.path.append(root)\n"
    "import namingTool\n"
    "namingTool.show()"
).format(root=TOOL_ROOT)


def _persist_path():
    try:
        import maya.cmds as cmds  # type: ignore
    except ImportError:
        return
    scripts_dir = os.path.join(cmds.internalVar(userAppDir=True), "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    user_setup = os.path.join(scripts_dir, "userSetup.py")
    marker = "# --- Naming Tool path ---"
    block = (f"{marker}\nimport sys\n"
             f"if r'{TOOL_ROOT}' not in sys.path:\n"
             f"    sys.path.append(r'{TOOL_ROOT}')\n")
    existing = ""
    if os.path.isfile(user_setup):
        with open(user_setup, "r", encoding="utf-8") as fh:
            existing = fh.read()
    if marker not in existing:
        with open(user_setup, "a", encoding="utf-8") as fh:
            fh.write("\n" + block)


def _create_shelf_button():
    import maya.cmds as cmds  # type: ignore
    import maya.mel as mel  # type: ignore

    shelf = mel.eval("global string $gShelfTopLevel; tabLayout -q -selectTab $gShelfTopLevel;")
    cmds.shelfButton(
        parent=shelf,
        label="NamingTool",
        annotation="Naming Tool - rename & validate asset names",
        image="commandButton.png",
        imageOverlayLabel="NAME",
        command=BUTTON_COMMAND,
        sourceType="python",
    )


def onMayaDroppedPythonFile(*args, **kwargs):  # noqa: N802 (Maya-required name)
    import sys

    if TOOL_ROOT not in sys.path:
        sys.path.append(TOOL_ROOT)

    _persist_path()
    try:
        _create_shelf_button()
        import maya.cmds as cmds  # type: ignore
        cmds.inViewMessage(amg="<hl>Naming Tool</hl> installe (bouton shelf ajoute).",
                           pos="midCenter", fade=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[Naming Tool] Installation partielle: {exc}")

    import namingTool
    namingTool.show()
