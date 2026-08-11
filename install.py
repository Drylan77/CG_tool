"""Drag-and-drop installer for the CG Asset Renamer (Maya 2025.3).

HOW TO INSTALL
--------------
Drag this file (``install.py``) from a file browser into a running Maya
viewport. Maya will execute :func:`onMayaDroppedPythonFile`, which:

    1. adds this tool's ``src`` folder to Maya's Python path (persisted via a
       small line appended to the user ``userSetup.py``),
    2. creates a shelf button on the current shelf that opens the tool.

You can also install manually - see README.md.
"""

from __future__ import annotations

import os


TOOL_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(TOOL_ROOT, "src")
BUTTON_LABEL = "CGRenamer"
BUTTON_COMMAND = (
    "import sys\n"
    "src = r'{src}'\n"
    "if src not in sys.path:\n"
    "    sys.path.append(src)\n"
    "import cg_renamer.launch as launch\n"
    "launch.main()"
).format(src=SRC_DIR)


def _persist_path() -> None:
    """Append the src dir to userSetup.py so imports work after restart."""
    try:
        import maya.cmds as cmds  # type: ignore
    except ImportError:
        return
    scripts_dir = os.path.join(cmds.internalVar(userAppDir=True), "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    user_setup = os.path.join(scripts_dir, "userSetup.py")
    marker = "# --- CG Asset Renamer path ---"
    line = f"{marker}\nimport sys\nif r'{SRC_DIR}' not in sys.path:\n    sys.path.append(r'{SRC_DIR}')\n"
    existing = ""
    if os.path.isfile(user_setup):
        with open(user_setup, "r", encoding="utf-8") as fh:
            existing = fh.read()
    if marker not in existing:
        with open(user_setup, "a", encoding="utf-8") as fh:
            fh.write("\n" + line)


def _create_shelf_button() -> None:
    import maya.cmds as cmds  # type: ignore
    import maya.mel as mel  # type: ignore

    current_shelf = mel.eval("global string $gShelfTopLevel; tabLayout -q -selectTab $gShelfTopLevel;")
    icon = os.path.join(TOOL_ROOT, "icons", "cg_renamer.png")
    icon = icon if os.path.isfile(icon) else "commandButton.png"
    cmds.shelfButton(
        parent=current_shelf,
        label=BUTTON_LABEL,
        annotation="CG Asset Renamer - rename & check asset names",
        image=icon,
        imageOverlayLabel="RENM",
        command=BUTTON_COMMAND,
        sourceType="python",
    )


def onMayaDroppedPythonFile(*args, **kwargs):  # noqa: N802 (Maya-required name)
    import sys

    if SRC_DIR not in sys.path:
        sys.path.append(SRC_DIR)

    _persist_path()
    try:
        _create_shelf_button()
        import maya.cmds as cmds  # type: ignore
        cmds.inViewMessage(
            amg="<hl>CG Asset Renamer</hl> installe. Bouton ajoute a la shelf courante.",
            pos="midCenter",
            fade=True,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[CG Renamer] Installation partielle: {exc}")

    # open the tool right away
    import cg_renamer.launch as launch
    launch.main()
