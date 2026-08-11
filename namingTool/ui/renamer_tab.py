"""Renamer tab: rename & number, prefix/suffix presets, search & replace,
auto-suffix, side detection and cleanup."""

from __future__ import annotations

import logging

from PySide6 import QtWidgets

from ..core import renamer

log = logging.getLogger("namingTool")


class RenamerTab(QtWidgets.QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._build_ui()

    # ------------------------------------------------------------------ #
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # -- rename & number ------------------------------------------- #
        rn_box = QtWidgets.QGroupBox("Rename & Number")
        rn = QtWidgets.QGridLayout(rn_box)
        rn.addWidget(QtWidgets.QLabel("Descriptor"), 0, 0)
        self.base_edit = QtWidgets.QLineEdit()
        self.base_edit.setPlaceholderText("ex: chairLeg")
        rn.addWidget(self.base_edit, 0, 1)
        rn.addWidget(QtWidgets.QLabel("Side"), 0, 2)
        self.side_combo = QtWidgets.QComboBox()
        rn.addWidget(self.side_combo, 0, 3)
        rn.addWidget(QtWidgets.QLabel("Suffix"), 1, 0)
        self.suffix_combo = QtWidgets.QComboBox()
        rn.addWidget(self.suffix_combo, 1, 1)
        rn.addWidget(QtWidgets.QLabel("Padding"), 1, 2)
        self.padding_spin = QtWidgets.QSpinBox()
        self.padding_spin.setRange(1, 4)
        rn.addWidget(self.padding_spin, 1, 3)
        apply_btn = QtWidgets.QPushButton("Rename & Number")
        apply_btn.clicked.connect(self._on_rename_number)
        rn.addWidget(apply_btn, 2, 0, 1, 4)
        layout.addWidget(rn_box)

        # -- prefix / suffix presets ----------------------------------- #
        px_box = QtWidgets.QGroupBox("Prefix / Suffix rapides")
        self.px_layout = QtWidgets.QGridLayout(px_box)
        layout.addWidget(px_box)

        # -- search & replace ------------------------------------------ #
        sr_box = QtWidgets.QGroupBox("Search & Replace")
        sr = QtWidgets.QGridLayout(sr_box)
        sr.addWidget(QtWidgets.QLabel("Search"), 0, 0)
        self.search_edit = QtWidgets.QLineEdit()
        sr.addWidget(self.search_edit, 0, 1)
        sr.addWidget(QtWidgets.QLabel("Replace"), 1, 0)
        self.replace_edit = QtWidgets.QLineEdit()
        sr.addWidget(self.replace_edit, 1, 1)
        self.wildcard_cb = QtWidgets.QCheckBox("Wildcards (*)")
        self.case_cb = QtWidgets.QCheckBox("Case sensitive")
        self.case_cb.setChecked(True)
        sr.addWidget(self.wildcard_cb, 2, 0)
        sr.addWidget(self.case_cb, 2, 1)
        sr_btn = QtWidgets.QPushButton("Search & Replace")
        sr_btn.clicked.connect(self._on_search_replace)
        sr.addWidget(sr_btn, 3, 0, 1, 2)
        layout.addWidget(sr_box)

        # -- one-click tools ------------------------------------------- #
        tools = QtWidgets.QGridLayout()
        self.auto_btn = QtWidgets.QPushButton("Auto Suffix (par type de noeud)")
        self.auto_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.auto_btn.clicked.connect(self._on_auto_suffix)
        self.side_btn = QtWidgets.QPushButton("Side by BBox (L/R)")
        self.side_btn.clicked.connect(self._on_side_bbox)
        self.clean_btn = QtWidgets.QPushButton("Cleanup (illegal / camelCase / namespaces)")
        self.clean_btn.clicked.connect(self._on_cleanup)
        tools.addWidget(self.auto_btn, 0, 0, 1, 2)
        tools.addWidget(self.side_btn, 1, 0)
        tools.addWidget(self.clean_btn, 1, 1)
        layout.addLayout(tools)

        layout.addStretch(1)
        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.rebuild_presets(self.window.config)

    # ------------------------------------------------------------------ #
    def rebuild_presets(self, config):
        """(Re)populate combos and preset buttons from the config."""
        self.padding_spin.setValue(int(config.get("padding", 2)))

        self.side_combo.clear()
        self.side_combo.addItem("(none)", "")
        for label, value in config.get("sides", {}).items():
            self.side_combo.addItem(f"{value}  ({label})", value)

        from ..core.config import valid_suffixes
        self.suffix_combo.clear()
        for code in valid_suffixes(config):
            self.suffix_combo.addItem(code, code)
        geo_idx = self.suffix_combo.findData(config.get("suffixes", {}).get("geometry", "GEO"))
        if geo_idx >= 0:
            self.suffix_combo.setCurrentIndex(geo_idx)

        # clear preset grid
        while self.px_layout.count():
            item = self.px_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        col = 0
        row = 0
        for label, value in config.get("sides", {}).items():
            b = QtWidgets.QPushButton(f"{value}_")
            b.setToolTip(f"Prefix {label}")
            b.clicked.connect(lambda _=False, v=value: self._affix(v, "prefix"))
            self.px_layout.addWidget(b, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1
        row += 1
        col = 0
        for code in valid_suffixes(config):
            b = QtWidgets.QPushButton(f"_{code}")
            b.clicked.connect(lambda _=False, v=code: self._affix(v, "suffix"))
            self.px_layout.addWidget(b, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1

    # ------------------------------------------------------------------ #
    def _nodes(self):
        from ..core import maya_utils
        scope = self.window.current_scope()
        if scope == "selection":
            return None  # renamer defaults to selection
        return maya_utils.list_nodes(scope=scope, node_type="transform")

    def _report(self, entries, title):
        ok = sum(1 for e in entries if e.status == "ok")
        err = [e for e in entries if e.status == "error"]
        msg = f"{title}: {ok} renomme(s)."
        if err:
            msg += f" {len(err)} erreur(s)."
        self.status.setText(msg)

    def _run(self, func, title, *args, **kwargs):
        try:
            entries = func(*args, **kwargs)
        except RuntimeError as exc:
            QtWidgets.QMessageBox.warning(self, title, str(exc))
            return
        self._report(entries, title)

    # -- slots ---------------------------------------------------------- #
    def _on_rename_number(self):
        cfg = dict(self.window.config)
        cfg["padding"] = self.padding_spin.value()
        base = self.base_edit.text().strip()
        if not base:
            QtWidgets.QMessageBox.warning(self, "Rename", "Descriptor requis.")
            return
        self._run(renamer.rename_and_number, "Rename & Number",
                  base, self.suffix_combo.currentData(), cfg,
                  side=self.side_combo.currentData(), nodes=self._nodes())

    def _affix(self, value, where):
        self._run(renamer.add_affix, f"{where.title()} {value}",
                  value, where, self.window.config, nodes=self._nodes())

    def _on_search_replace(self):
        self._run(renamer.search_replace, "Search & Replace",
                  self.search_edit.text(), self.replace_edit.text(), self.window.config,
                  nodes=self._nodes(), use_wildcard=self.wildcard_cb.isChecked(),
                  case_sensitive=self.case_cb.isChecked())

    def _on_auto_suffix(self):
        self._run(renamer.auto_suffix, "Auto Suffix", self.window.config, nodes=self._nodes())

    def _on_side_bbox(self):
        self._run(renamer.side_by_bbox, "Side by BBox", self.window.config, nodes=self._nodes())

    def _on_cleanup(self):
        self._run(renamer.cleanup, "Cleanup", self.window.config, nodes=self._nodes())
