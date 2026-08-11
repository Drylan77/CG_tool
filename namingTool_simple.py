"""Naming Tool - version COMPLETE autonome (un seul fichier) pour Maya 2025.3.

UTILISATION - le plus simple possible :
    1. Ouvre Maya 2025.3
    2. Script Editor -> onglet Python
    3. Copie-colle TOUT ce fichier
    4. Execute (Ctrl+Entree)  ->  la fenetre s'ouvre

Convention : [side]_[descriptor][increment]_[SUFFIX]
    ex : L_doorHandle_GEO   wheelFront01_GEO   C_body_GRP

Tous les outils dans un seul fichier :
  Onglet Renamer  : Rename & Number, prefixes/suffixes rapides,
                    Search & Replace, Auto Suffix, Side by BBox, Cleanup
  Onglet Validator: Run All Checks, liste cliquable des noeuds fautifs, Fix

Aucune dependance externe : PySide6 + maya.cmds (fournis par Maya 2025).
"""

import fnmatch
import re

from PySide6 import QtWidgets, QtCore, QtGui
from shiboken6 import wrapInstance
import maya.OpenMayaUI as omui
import maya.cmds as cmds


# ========================================================================== #
#  CONVENTION (modifiable ici)
# ========================================================================== #
SIDES = {"(aucun)": "", "Left": "L", "Right": "R", "Center": "C",
         "Front": "F", "Back": "B", "Top": "T", "Bottom": "Bt"}
SUFFIXES = ["GEO", "GRP", "LOC", "CRV", "NRB", "PLY", "CAM", "LGT",
            "JNT", "CTL", "MAT", "SG", "TEX", "DEF", "CNS", "PXY"]
GEO_SUFFIX = "GEO"
PADDING = 2

# type de node Maya -> suffixe (pour l'Auto Suffix)
TYPE_TO_SUFFIX = {
    "mesh": "GEO", "nurbsSurface": "NRB", "subdiv": "GEO",
    "nurbsCurve": "CRV", "bezierCurve": "CRV", "locator": "LOC",
    "camera": "CAM", "joint": "JNT",
    "pointLight": "LGT", "spotLight": "LGT",
    "directionalLight": "LGT", "areaLight": "LGT",
}
DEFAULT_NAME_PATTERNS = ["pCube", "pSphere", "pCylinder", "pPlane", "pTorus",
                         "pCone", "pPipe", "pPrism", "pSolid", "polySurface",
                         "transform", "group", "null", "locator",
                         "nurbsCircle", "curve", "joint"]
FORBIDDEN_WORDS = ["final", "new", "test", "temp", "copy", "pasted", "ok"]
PROTECTED = {"persp", "top", "front", "side", "initialShadingGroup", "lambert1"}

NAME_RE = re.compile(
    r"^(?:(%s)_)?([a-z][a-zA-Z0-9]*?)(\d{2,3})?_(%s)$"
    % ("|".join(sorted({v for v in SIDES.values() if v}, key=len, reverse=True)),
       "|".join(SUFFIXES))
)
DEFAULT_RE = re.compile(r"^(?:%s)\d*$" % "|".join(DEFAULT_NAME_PATTERNS))


# ========================================================================== #
#  LOGIQUE NOMS (sans Maya)
# ========================================================================== #
def to_camel(text):
    words = [w for w in re.split(r"[^A-Za-z0-9]+", text.strip()) if w]
    if not words:
        return ""
    out = words[0][:1].lower() + words[0][1:]
    for w in words[1:]:
        out += w[:1].upper() + w[1:]
    return out.lstrip("0123456789")


def build_name(descriptor, suffix, side="", index=None, padding=PADDING):
    desc = to_camel(descriptor)
    if not desc:
        raise ValueError("Descriptor requis.")
    core = desc + (str(index).zfill(padding) if index is not None else "")
    return "_".join([p for p in (side, core, suffix) if p])


def is_valid(name):
    return NAME_RE.match(name) is not None


def name_errors(name):
    """Retourne la liste des problemes d'un nom (vide si conforme)."""
    if is_valid(name):
        return [w for w in FORBIDDEN_WORDS if w in name.lower() and "mot interdit"]
    errs = []
    if re.search(r"[^A-Za-z0-9_]", name):
        errs.append("caracteres illegaux")
    if name[:1].isdigit():
        errs.append("commence par un chiffre")
    if "__" in name:
        errs.append("double underscore")
    tokens = [t for t in name.split("_") if t]
    if len(tokens) < 2 or tokens[-1] not in SUFFIXES:
        errs.append("suffixe manquant/invalide")
    body = tokens[:-1]
    if body and body[0] in SIDES.values():
        body = body[1:]
    if body and not re.match(r"^[a-z][a-zA-Z0-9]*$", body[0]):
        errs.append("descriptor pas en camelCase")
    return errs or ["non conforme"]


# ========================================================================== #
#  HELPERS MAYA
# ========================================================================== #
def short(node):
    return node.split("|")[-1].split(":")[-1]


def short_ns(node):
    return node.split("|")[-1]


def unique(name):
    if not cmds.objExists(name):
        return name
    i = 1
    while cmds.objExists("%s%02d" % (name, i)):
        i += 1
    return "%s%02d" % (name, i)


def deepest_first(nodes):
    return sorted(nodes, key=lambda n: n.count("|"), reverse=True)


def suffix_for_node(node):
    ntype = cmds.nodeType(node)
    if ntype in TYPE_TO_SUFFIX:
        return TYPE_TO_SUFFIX[ntype]
    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    if shapes:
        return TYPE_TO_SUFFIX.get(cmds.nodeType(shapes[0]), None)
    return "GRP"  # transform sans shape = groupe


def scene_transforms():
    nodes = cmds.ls(dag=True, type="transform", long=True) or []
    return [n for n in nodes if short(n) not in PROTECTED]


def selection_or_scene(scope):
    if scope == "scene":
        return scene_transforms()
    sel = cmds.ls(selection=True, long=True) or []
    return [n for n in sel if short(n) not in PROTECTED]


def undo(func):
    """Decorateur : encapsule l'operation dans un seul undo."""
    def wrap(*a, **k):
        cmds.undoInfo(openChunk=True)
        try:
            return func(*a, **k)
        finally:
            cmds.undoInfo(closeChunk=True)
    return wrap


# ========================================================================== #
#  OPERATIONS DE RENAME
# ========================================================================== #
@undo
def op_rename_number(nodes, descriptor, suffix, side, padding):
    order = {n: i for i, n in enumerate(nodes)}
    multi = len(nodes) > 1
    count = 0
    for node in deepest_first(nodes):
        idx = order[node] + 1 if multi else None
        target = unique(build_name(descriptor, suffix, side=side, index=idx, padding=padding))
        cmds.rename(node, target)
        count += 1
    return count


@undo
def op_affix(nodes, affix, where):
    affix = affix.strip("_")
    count = 0
    for node in deepest_first(nodes):
        name = short(node)
        tokens = name.split("_")
        if where == "prefix":
            new = name if tokens and tokens[0] == affix else "%s_%s" % (affix, name)
        else:
            new = name if tokens and tokens[-1] == affix else "%s_%s" % (name, affix)
        if new != name:
            cmds.rename(node, unique(new))
            count += 1
    return count


@undo
def op_search_replace(nodes, search, replace, wildcard, case_sensitive):
    flags = 0 if case_sensitive else re.IGNORECASE
    pat = re.compile(fnmatch.translate(search) if wildcard else re.escape(search), flags)
    count = 0
    for node in deepest_first(nodes):
        name = short(node)
        new = pat.sub(replace, name)
        if new != name:
            cmds.rename(node, unique(new))
            count += 1
    return count


@undo
def op_auto_suffix(nodes):
    count = 0
    for node in deepest_first(nodes):
        suf = suffix_for_node(node)
        if not suf:
            continue
        tokens = short(node).split("_")
        if tokens[-1] in SUFFIXES:
            tokens[-1] = suf
        else:
            tokens.append(suf)
        cmds.rename(node, unique("_".join(tokens)))
        count += 1
    return count


@undo
def op_side_bbox(nodes):
    count = 0
    for node in deepest_first(nodes):
        bbox = cmds.xform(node, q=True, ws=True, boundingBox=True)
        cx = (bbox[0] + bbox[3]) / 2.0
        side = "C" if abs(cx) < 1e-4 else ("L" if cx > 0 else "R")
        name = short(node)
        if name.split("_")[0] != side:
            cmds.rename(node, unique("%s_%s" % (side, name)))
            count += 1
    return count


@undo
def op_cleanup(nodes, remove_ns=True):
    count = 0
    for node in deepest_first(nodes):
        name = short_ns(node)
        if remove_ns:
            name = name.split(":")[-1]
        name = name.replace("pasted__", "").replace("pasted_", "")
        tokens = [t for t in name.split("_") if t]
        suffix = tokens.pop() if tokens and tokens[-1] in SUFFIXES else ""
        desc = to_camel("_".join(tokens))
        new = desc + ("_" + suffix if suffix else "")
        if new and new != short(node):
            cmds.rename(node, unique(new))
            count += 1
    return count


# ========================================================================== #
#  CHECKS + FIX
# ========================================================================== #
def run_checks(nodes):
    """Retourne une liste de (cle, label, statut, [noeuds], fixable)."""
    results = []

    bad = [n for n in nodes if DEFAULT_RE.match(short(n))]
    results.append(("default", "Noms par defaut Maya", bool(bad), bad, True))

    from collections import Counter
    counts = Counter(short(n) for n in nodes)
    dupes = {k for k, c in counts.items() if c > 1}
    bad = [n for n in nodes if short(n) in dupes]
    results.append(("dupes", "Duplicate short names", bool(bad), bad, True))

    bad = [n for n in nodes if short(n).split("_")[-1] not in SUFFIXES
           or len(short(n).split("_")) < 2]
    results.append(("suffix", "Suffixe present et valide", bool(bad), bad, True))

    bad = []
    for n in nodes:
        exp = suffix_for_node(n)
        cur = short(n).split("_")[-1]
        if exp and cur in SUFFIXES and cur != exp:
            bad.append(n)
    results.append(("suffix_type", "Suffixe coherent avec le type", bool(bad), bad, True))

    bad = [n for n in nodes if name_errors(short(n))]
    results.append(("convention", "Caracteres / casse / convention", bool(bad), bad, True))

    bad = []
    for n in nodes:
        base = short(n)
        for shp in cmds.listRelatives(n, shapes=True, fullPath=True) or []:
            if short(shp) != base + "Shape":
                bad.append(n)
                break
    results.append(("shape", "Shapes synchronisees", bool(bad), bad, True))

    bad = [n for n in nodes if ":" in short_ns(n)]
    results.append(("namespace", "Absence de namespaces", bool(bad), bad, True))

    bad = []
    for n in nodes:
        parent = cmds.listRelatives(n, parent=True, fullPath=True)
        if parent is None and short(n).split("_")[-1] == GEO_SUFFIX:
            bad.append(n)
        if cmds.nodeType(n) == "transform" and not (cmds.listRelatives(n, shapes=True) or []):
            if not (cmds.listRelatives(n, children=True) or []):
                bad.append(n)
    results.append(("hierarchy", "Hierarchie (orphelins/groupes vides)", bool(bad), list(dict.fromkeys(bad)), False))

    return results


@undo
def fix_check(key, nodes):
    if key in ("suffix", "suffix_type"):
        return _auto(nodes)
    if key == "default":
        _auto(nodes)
        return _clean(nodes)
    if key == "convention":
        return _clean(nodes)
    if key == "namespace":
        return _clean(nodes, remove_ns=True)
    if key == "shape":
        n = 0
        for node in nodes:
            base = short(node)
            for shp in cmds.listRelatives(node, shapes=True, fullPath=True) or []:
                if short(shp) != base + "Shape":
                    cmds.rename(shp, unique(base + "Shape"))
                    n += 1
        return n
    if key == "dupes":
        n = 0
        for node in deepest_first(nodes):
            u = unique(short(node))
            if u != short(node):
                cmds.rename(node, u)
                n += 1
        return n
    return 0


# versions non-decorees (le fix_check gere deja l'undo global)
def _auto(nodes):
    count = 0
    for node in deepest_first(nodes):
        suf = suffix_for_node(node)
        if not suf:
            continue
        tokens = short(node).split("_")
        if tokens[-1] in SUFFIXES:
            tokens[-1] = suf
        else:
            tokens.append(suf)
        cmds.rename(node, unique("_".join(tokens)))
        count += 1
    return count


def _clean(nodes, remove_ns=True):
    count = 0
    for node in deepest_first(nodes):
        name = short_ns(node)
        if remove_ns:
            name = name.split(":")[-1]
        name = name.replace("pasted__", "").replace("pasted_", "")
        tokens = [t for t in name.split("_") if t]
        suffix = tokens.pop() if tokens and tokens[-1] in SUFFIXES else ""
        desc = to_camel("_".join(tokens))
        new = desc + ("_" + suffix if suffix else "")
        if new and new != short(node):
            cmds.rename(node, unique(new))
            count += 1
    return count


# ========================================================================== #
#  UI
# ========================================================================== #
def maya_window():
    return wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)


class NamingTool(QtWidgets.QDialog):
    def __init__(self, parent=maya_window()):
        super().__init__(parent)
        self.setWindowTitle("Naming Tool")
        self.setMinimumSize(480, 560)
        self._build()

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)

        # scope
        scope_row = QtWidgets.QHBoxLayout()
        scope_row.addWidget(QtWidgets.QLabel("Portee:"))
        self.rb_sel = QtWidgets.QRadioButton("Selection")
        self.rb_scene = QtWidgets.QRadioButton("Scene")
        self.rb_sel.setChecked(True)
        scope_row.addWidget(self.rb_sel)
        scope_row.addWidget(self.rb_scene)
        scope_row.addStretch(1)
        root.addLayout(scope_row)

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._renamer_tab(), "Renamer")
        tabs.addTab(self._validator_tab(), "Validator")
        root.addWidget(tabs, 1)

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color:#8bd;")
        root.addWidget(self.status)

    def _scope(self):
        return "scene" if self.rb_scene.isChecked() else "selection"

    def _nodes(self):
        nodes = selection_or_scene(self._scope())
        if not nodes:
            raise RuntimeError("Aucun objet (selection vide / scene vide).")
        return nodes

    def _run(self, label, func, *a, **k):
        try:
            n = func(self._nodes(), *a, **k)
        except (RuntimeError, ValueError) as exc:
            self.status.setText("%s : %s" % (label, exc))
            return
        self.status.setText("%s : %s objet(s) traite(s)." % (label, n))

    # -- Renamer ------------------------------------------------------- #
    def _renamer_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)

        # rename & number
        box = QtWidgets.QGroupBox("Rename & Number")
        g = QtWidgets.QGridLayout(box)
        self.desc = QtWidgets.QLineEdit()
        self.desc.setPlaceholderText("ex: doorHandle")
        self.desc.textChanged.connect(self._preview)
        self.side = QtWidgets.QComboBox(); self.side.addItems(SIDES.keys())
        self.side.currentIndexChanged.connect(self._preview)
        self.suffix = QtWidgets.QComboBox(); self.suffix.addItems(SUFFIXES)
        self.suffix.currentIndexChanged.connect(self._preview)
        self.pad = QtWidgets.QSpinBox(); self.pad.setRange(1, 4); self.pad.setValue(PADDING)
        g.addWidget(QtWidgets.QLabel("Descriptor"), 0, 0); g.addWidget(self.desc, 0, 1, 1, 3)
        g.addWidget(QtWidgets.QLabel("Side"), 1, 0); g.addWidget(self.side, 1, 1)
        g.addWidget(QtWidgets.QLabel("Suffix"), 1, 2); g.addWidget(self.suffix, 1, 3)
        g.addWidget(QtWidgets.QLabel("Padding"), 2, 0); g.addWidget(self.pad, 2, 1)
        self.prev = QtWidgets.QLabel("-")
        self.prev.setStyleSheet("font-family:monospace; color:#7fd37f; padding:5px;"
                                "background:#2b2b2b; border-radius:4px;")
        g.addWidget(self.prev, 3, 0, 1, 4)
        b = QtWidgets.QPushButton("Rename & Number")
        b.clicked.connect(self._do_rename)
        g.addWidget(b, 4, 0, 1, 4)
        lay.addWidget(box)

        # prefixes / suffixes rapides
        box2 = QtWidgets.QGroupBox("Prefix / Suffix rapides")
        pg = QtWidgets.QGridLayout(box2)
        col = 0
        for label, val in SIDES.items():
            if not val:
                continue
            btn = QtWidgets.QPushButton("%s_" % val)
            btn.clicked.connect(lambda _=False, v=val: self._run("Prefix", op_affix, v, "prefix"))
            pg.addWidget(btn, 0, col); col += 1
        row = 1; col = 0
        for code in SUFFIXES:
            btn = QtWidgets.QPushButton("_%s" % code)
            btn.clicked.connect(lambda _=False, v=code: self._run("Suffix", op_affix, v, "suffix"))
            pg.addWidget(btn, row, col); col += 1
            if col >= 6:
                col = 0; row += 1
        lay.addWidget(box2)

        # search & replace
        box3 = QtWidgets.QGroupBox("Search & Replace")
        sg = QtWidgets.QGridLayout(box3)
        self.search = QtWidgets.QLineEdit(); self.replace = QtWidgets.QLineEdit()
        self.cb_wild = QtWidgets.QCheckBox("Wildcards *")
        self.cb_case = QtWidgets.QCheckBox("Case sensitive"); self.cb_case.setChecked(True)
        sg.addWidget(QtWidgets.QLabel("Search"), 0, 0); sg.addWidget(self.search, 0, 1)
        sg.addWidget(QtWidgets.QLabel("Replace"), 1, 0); sg.addWidget(self.replace, 1, 1)
        sg.addWidget(self.cb_wild, 2, 0); sg.addWidget(self.cb_case, 2, 1)
        b3 = QtWidgets.QPushButton("Search & Replace")
        b3.clicked.connect(lambda: self._run(
            "Search&Replace", op_search_replace, self.search.text(), self.replace.text(),
            self.cb_wild.isChecked(), self.cb_case.isChecked()))
        sg.addWidget(b3, 3, 0, 1, 2)
        lay.addWidget(box3)

        # one-click tools
        grid = QtWidgets.QGridLayout()
        b_auto = QtWidgets.QPushButton("Auto Suffix (par type)")
        b_auto.setStyleSheet("font-weight:bold; padding:6px;")
        b_auto.clicked.connect(lambda: self._run("Auto Suffix", op_auto_suffix))
        b_side = QtWidgets.QPushButton("Side by BBox (L/R)")
        b_side.clicked.connect(lambda: self._run("Side BBox", op_side_bbox))
        b_clean = QtWidgets.QPushButton("Cleanup")
        b_clean.clicked.connect(lambda: self._run("Cleanup", op_cleanup))
        grid.addWidget(b_auto, 0, 0, 1, 2)
        grid.addWidget(b_side, 1, 0); grid.addWidget(b_clean, 1, 1)
        lay.addLayout(grid)
        lay.addStretch(1)

        self._preview()
        return w

    def _preview(self):
        try:
            self.prev.setText(build_name(self.desc.text(), self.suffix.currentText(),
                                         side=SIDES[self.side.currentText()],
                                         padding=self.pad.value()))
        except ValueError:
            self.prev.setText("[descriptor requis]")

    def _do_rename(self):
        self._run("Rename & Number", op_rename_number, self.desc.text(),
                  self.suffix.currentText(), SIDES[self.side.currentText()], self.pad.value())

    # -- Validator ----------------------------------------------------- #
    def _validator_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        top = QtWidgets.QHBoxLayout()
        b_run = QtWidgets.QPushButton("Run All Checks")
        b_run.setStyleSheet("font-weight:bold; padding:6px;")
        b_run.clicked.connect(self._do_check)
        b_sel = QtWidgets.QPushButton("Select Errors")
        b_sel.clicked.connect(self._select_errors)
        top.addWidget(b_run, 1); top.addWidget(b_sel)
        lay.addLayout(top)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Check", "Statut", "Nb", "Fix"])
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.tree.itemClicked.connect(self._check_clicked)
        lay.addWidget(self.tree, 1)

        lay.addWidget(QtWidgets.QLabel("Noeuds fautifs (clic = select) :"))
        self.node_list = QtWidgets.QListWidget()
        self.node_list.setMaximumHeight(140)
        self.node_list.itemClicked.connect(self._node_clicked)
        lay.addWidget(self.node_list)

        self.summary = QtWidgets.QLabel("")
        self.summary.setStyleSheet("font-weight:bold;")
        lay.addWidget(self.summary)
        self._results = []
        return w

    def _do_check(self):
        try:
            nodes = self._nodes()
        except RuntimeError as exc:
            self.summary.setText(str(exc)); return
        self._results = run_checks(nodes)
        self.tree.clear(); self.node_list.clear()
        errs = 0
        for key, label, failed, bad, fixable in self._results:
            errs += 1 if failed else 0
            item = QtWidgets.QTreeWidgetItem([label, "X" if failed else "OK",
                                              str(len(bad)), "Fix" if (failed and fixable) else ""])
            item.setForeground(1, QtGui.QBrush(QtGui.QColor("#e06c6c" if failed else "#7fd37f")))
            item.setData(0, QtCore.Qt.UserRole, key)
            self.tree.addTopLevelItem(item)
        total = len(self._results)
        self.summary.setText("%d checks - %d OK, %d en erreur" % (total, total - errs, errs))

    def _check_clicked(self, item, column):
        key = item.data(0, QtCore.Qt.UserRole)
        entry = next((r for r in self._results if r[0] == key), None)
        if not entry:
            return
        _, label, failed, bad, fixable = entry
        if column == 3 and failed and fixable:
            n = fix_check(key, bad)
            self.summary.setText("%s : %d corrige(s)." % (label, n))
            self._do_check()
            return
        self.node_list.clear()
        for node in bad:
            it = QtWidgets.QListWidgetItem(short(node))
            it.setData(QtCore.Qt.UserRole, node)
            self.node_list.addItem(it)

    def _node_clicked(self, item):
        node = item.data(QtCore.Qt.UserRole)
        if cmds.objExists(node):
            cmds.select(node, replace=True)

    def _select_errors(self):
        nodes = [n for r in self._results if r[2] for n in r[3]]
        if nodes:
            cmds.select([n for n in nodes if cmds.objExists(n)], replace=True)


# ========================================================================== #
#  LANCEMENT
# ========================================================================== #
try:
    _naming_win.close()  # noqa: F821
    _naming_win.deleteLater()  # noqa: F821
except Exception:
    pass
_naming_win = NamingTool()
_naming_win.show()
