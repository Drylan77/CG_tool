"""Naming Tool - version SIMPLE autonome (un seul fichier) pour Maya 2025.3.

UTILISATION - le plus simple possible :
    1. Ouvre Maya 2025.3
    2. Script Editor -> onglet Python
    3. Copie-colle TOUT ce fichier
    4. Execute (Ctrl+Entree)  ->  la fenetre s'ouvre

Convention : [side]_[descriptor][increment]_[SUFFIX]
    ex : L_doorHandle_GEO   wheelFront01_GEO   C_body_GRP

Aucune dependance : PySide6 + maya.cmds (fournis par Maya 2025).
"""

import re
from PySide6 import QtWidgets, QtCore
from shiboken6 import wrapInstance
import maya.OpenMayaUI as omui
import maya.cmds as cmds


# --- convention (modifiable ici) ------------------------------------------- #
SIDES = {"(aucun)": "", "Left": "L", "Right": "R", "Center": "C"}
SUFFIXES = ["GEO", "GRP", "LOC", "CRV", "NRB", "CAM", "LGT", "JNT", "CTL", "PXY"]
# type de shape Maya -> suffixe, pour l'Auto Suffix
TYPE_TO_SUFFIX = {
    "mesh": "GEO", "nurbsSurface": "NRB", "nurbsCurve": "CRV",
    "locator": "LOC", "camera": "CAM", "joint": "JNT",
    "pointLight": "LGT", "spotLight": "LGT", "directionalLight": "LGT",
}
NAME_RE = re.compile(r"^(?:(L|R|C)_)?([a-z][a-zA-Z0-9]*?)(\d{2,3})?_(%s)$" % "|".join(SUFFIXES))


# --- logique --------------------------------------------------------------- #
def to_camel(text):
    words = [w for w in re.split(r"[^A-Za-z0-9]+", text.strip()) if w]
    if not words:
        return ""
    out = words[0][:1].lower() + words[0][1:]
    for w in words[1:]:
        out += w[:1].upper() + w[1:]
    return out.lstrip("0123456789")


def build_name(descriptor, suffix, side="", index=None, padding=2):
    desc = to_camel(descriptor)
    if not desc:
        raise ValueError("Descriptor requis.")
    core = desc + (str(index).zfill(padding) if index is not None else "")
    return "_".join([p for p in (side, core, suffix) if p])


def is_valid(name):
    return NAME_RE.match(name) is not None


def suffix_for_node(node):
    ntype = cmds.nodeType(node)
    if ntype in TYPE_TO_SUFFIX:
        return TYPE_TO_SUFFIX[ntype]
    shapes = cmds.listRelatives(node, shapes=True) or []
    if shapes:
        return TYPE_TO_SUFFIX.get(cmds.nodeType(shapes[0]))
    return "GRP"  # transform sans shape = groupe


def unique(name):
    if not cmds.objExists(name):
        return name
    i = 1
    while cmds.objExists("%s%02d" % (name, i)):
        i += 1
    return "%s%02d" % (name, i)


# --- UI -------------------------------------------------------------------- #
def maya_window():
    return wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)


class NamingToolSimple(QtWidgets.QDialog):
    def __init__(self, parent=maya_window()):
        super().__init__(parent)
        self.setWindowTitle("Naming Tool (simple)")
        self.setMinimumWidth(420)
        self._build()

    def _build(self):
        lay = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        self.desc = QtWidgets.QLineEdit()
        self.desc.setPlaceholderText("ex: doorHandle")
        self.desc.textChanged.connect(self._preview)
        self.side = QtWidgets.QComboBox()
        self.side.addItems(SIDES.keys())
        self.side.currentIndexChanged.connect(self._preview)
        self.suffix = QtWidgets.QComboBox()
        self.suffix.addItems(SUFFIXES)
        self.suffix.currentIndexChanged.connect(self._preview)
        self.pad = QtWidgets.QSpinBox()
        self.pad.setRange(1, 4)
        self.pad.setValue(2)
        form.addRow("Descriptor", self.desc)
        form.addRow("Side", self.side)
        form.addRow("Suffix", self.suffix)
        form.addRow("Padding", self.pad)
        lay.addLayout(form)

        self.prev = QtWidgets.QLabel("-")
        self.prev.setStyleSheet("font-family:monospace; color:#7fd37f; padding:6px;"
                                "background:#2b2b2b; border-radius:4px;")
        lay.addWidget(self.prev)

        row = QtWidgets.QHBoxLayout()
        b_rename = QtWidgets.QPushButton("Rename selection")
        b_rename.clicked.connect(self._rename)
        b_auto = QtWidgets.QPushButton("Auto Suffix")
        b_auto.clicked.connect(self._auto_suffix)
        row.addWidget(b_rename)
        row.addWidget(b_auto)
        lay.addLayout(row)

        b_check = QtWidgets.QPushButton("Check scene")
        b_check.clicked.connect(self._check)
        lay.addWidget(b_check)

        self.out = QtWidgets.QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setMaximumHeight(160)
        lay.addWidget(self.out)

        self._preview()

    def _preview(self):
        try:
            n = build_name(self.desc.text(), self.suffix.currentText(),
                           side=SIDES[self.side.currentText()])
            self.prev.setText(n)
        except ValueError:
            self.prev.setText("[descriptor requis]")

    def _rename(self):
        sel = cmds.ls(selection=True, long=True)
        if not sel:
            cmds.warning("Rien de selectionne.")
            return
        side = SIDES[self.side.currentText()]
        pad = self.pad.value()
        multi = len(sel) > 1
        cmds.undoInfo(openChunk=True)
        try:
            for i, node in enumerate(sorted(sel, key=lambda x: x.count("|"), reverse=True), 1):
                idx = i if multi else None
                target = unique(build_name(self.desc.text(), self.suffix.currentText(),
                                           side=side, index=idx, padding=pad))
                cmds.rename(node, target)
        finally:
            cmds.undoInfo(closeChunk=True)
        self.out.setPlainText("%d objet(s) renomme(s)." % len(sel))

    def _auto_suffix(self):
        sel = cmds.ls(selection=True, long=True)
        if not sel:
            cmds.warning("Rien de selectionne.")
            return
        cmds.undoInfo(openChunk=True)
        n = 0
        try:
            for node in sorted(sel, key=lambda x: x.count("|"), reverse=True):
                suf = suffix_for_node(node)
                short = node.split("|")[-1]
                tokens = short.split("_")
                if tokens[-1] in SUFFIXES:
                    tokens[-1] = suf
                else:
                    tokens.append(suf)
                cmds.rename(node, unique("_".join(tokens)))
                n += 1
        finally:
            cmds.undoInfo(closeChunk=True)
        self.out.setPlainText("Auto Suffix applique a %d objet(s)." % n)

    def _check(self):
        nodes = cmds.ls(dag=True, type="transform", long=True) or []
        skip = {"persp", "top", "front", "side"}
        bad = []
        for node in nodes:
            short = node.split("|")[-1].split(":")[-1]
            if short in skip:
                continue
            if not is_valid(short):
                bad.append(short)
        if bad:
            self.out.setPlainText("%d nom(s) NON conforme(s):\n- %s"
                                  % (len(bad), "\n- ".join(bad)))
        else:
            self.out.setPlainText("Tous les noms sont conformes.")


# --- lancement ------------------------------------------------------------- #
try:
    _naming_win.close()  # noqa: F821
except Exception:
    pass
_naming_win = NamingToolSimple()
_naming_win.show()
