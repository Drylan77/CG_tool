"""Build a deliberately messy scene to test the Naming Tool inside Maya.

Run from Maya's Script Editor (Python tab):

    import sys; sys.path.append(r"CHEMIN/VERS/CG_tool")
    from tests import make_test_scene
    make_test_scene.build()

Then open the tool (``import namingTool; namingTool.show()``), set the scope to
"Scene", hit *Run All Checks*, and try *Auto Suffix* / *Fix* / *Cleanup*.

Note: Maya sanitises illegal characters on rename (``porte-gauche`` becomes
``porte_gauche``), so this scene focuses on the problems Maya actually lets you
create: default names, duplicates, missing / wrong suffixes, bad casing, shape
desync, empty groups, mixed numbering and namespaces.
"""

from __future__ import annotations


def build():
    import maya.cmds as cmds

    cmds.file(new=True, force=True)

    # --- default Maya names (untouched) --------------------------------- #
    cmds.polyCube()          # -> pCube1
    cmds.polyCube()          # -> pCube2
    cmds.group(empty=True)   # -> group1 (empty group)

    # --- duplicate short names in different branches -------------------- #
    grp_a = cmds.group(empty=True, name="branchA_GRP")
    grp_b = cmds.group(empty=True, name="branchB_GRP")
    ball_a = cmds.polyCube(name="ball_GEO")[0]
    cmds.parent(ball_a, grp_a)
    ball_b = cmds.polyCube(name="ball_GEO")[0]   # Maya makes it ball_GEO or ball_GEO1
    cmds.parent(ball_b, grp_b)
    cmds.rename(ball_b, "ball_GEO")              # force the duplicate short name

    # --- bad casing / missing / wrong suffix ---------------------------- #
    cmds.polyCube(name="Body_GEO")               # capital initial (bad camelCase)
    cmds.polyCube(name="handle")                 # missing suffix
    cmds.polySphere(name="wheel_XYZ")            # invalid suffix

    # --- mixed numbering ------------------------------------------------- #
    cmds.polyCube(name="leg1_GEO")
    cmds.polyCube(name="leg02_GEO")
    cmds.polyCube(name="leg003_GEO")

    # --- shape desync (transform ok, shape wrong) ----------------------- #
    trs = cmds.polyCube(name="crate_GEO")[0]
    shp = cmds.listRelatives(trs, shapes=True)[0]
    cmds.rename(shp, "someOtherShape")

    # --- namespace residue from an import ------------------------------- #
    if not cmds.namespace(exists="importedNS"):
        cmds.namespace(add="importedNS")
    cmds.polyCube(name="importedNS:prop_GEO")

    # --- a couple of already-valid names (should pass) ------------------ #
    cmds.polyCube(name="L_doorHandle_GEO")
    cmds.polyCube(name="C_body_GEO")

    cmds.select(clear=True)
    print("[make_test_scene] Scene de test creee. Ouvre le Naming Tool et lance Run All Checks (scope: Scene).")


if __name__ == "__main__":
    build()
