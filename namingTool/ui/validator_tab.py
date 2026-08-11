"""Validator tab: run checks, list offending nodes (clickable), fix, export."""

from __future__ import annotations

import json
import logging

from PySide6 import QtCore, QtGui, QtWidgets

from ..core import checks

log = logging.getLogger("namingTool")

_STATUS_COLOR = {
    checks.PASS: "#7fd37f",
    checks.WARNING: "#e0a86c",
    checks.ERROR: "#e06c6c",
}
_STATUS_ICON = {checks.PASS: "OK", checks.WARNING: "!", checks.ERROR: "X"}


class ValidatorTab(QtWidgets.QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._report = {}
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        run_btn = QtWidgets.QPushButton("Run All Checks")
        run_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        run_btn.clicked.connect(self._on_run_all)
        self.select_btn = QtWidgets.QPushButton("Select Errors")
        self.select_btn.clicked.connect(self._on_select_errors)
        self.export_btn = QtWidgets.QPushButton("Export Report")
        self.export_btn.clicked.connect(self._on_export)
        top.addWidget(run_btn, 1)
        top.addWidget(self.select_btn)
        top.addWidget(self.export_btn)
        layout.addLayout(top)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Check", "Status", "Count", "Fix"])
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree, 1)

        self.node_list = QtWidgets.QListWidget()
        self.node_list.setMaximumHeight(150)
        self.node_list.itemClicked.connect(self._on_node_clicked)
        layout.addWidget(QtWidgets.QLabel("Noeuds fautifs (clic = select) :"))
        layout.addWidget(self.node_list)

        self.summary = QtWidgets.QLabel("")
        self.summary.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.summary)

    # ------------------------------------------------------------------ #
    def _on_run_all(self):
        scope = self.window.current_scope()
        try:
            self._report = checks.run_all(scope=scope, config=self.window.config)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Validator", str(exc))
            return
        self._populate()

    def _populate(self):
        self.tree.clear()
        self.node_list.clear()
        for name, data in self._report.items():
            item = QtWidgets.QTreeWidgetItem([
                data.get("label", name),
                _STATUS_ICON.get(data["status"], "?"),
                str(len(data["nodes"])),
                "Fix" if (data.get("fixable") and data["nodes"]) else "",
            ])
            item.setForeground(1, QtGui.QBrush(QtGui.QColor(_STATUS_COLOR.get(data["status"], "#ccc"))))
            item.setData(0, QtCore.Qt.UserRole, name)
            item.setToolTip(0, data.get("message", ""))
            self.tree.addTopLevelItem(item)
        self.summary.setText(checks.summarize(self._report))

    def _on_item_clicked(self, item, column):
        name = item.data(0, QtCore.Qt.UserRole)
        data = self._report.get(name, {})
        # column 3 == Fix
        if column == 3 and data.get("fixable") and data["nodes"]:
            self._fix(name, data["nodes"])
            return
        self.node_list.clear()
        from ..core import maya_utils
        for node in data.get("nodes", []):
            it = QtWidgets.QListWidgetItem(maya_utils.short_name(node))
            it.setData(QtCore.Qt.UserRole, node)
            self.node_list.addItem(it)

    def _on_node_clicked(self, item):
        node = item.data(QtCore.Qt.UserRole)
        try:
            import maya.cmds as cmds  # type: ignore
            cmds.select(node, replace=True)
        except Exception:  # noqa: BLE001
            pass

    def _fix(self, name, nodes):
        try:
            fixed = checks.fix_check(name, nodes, config=self.window.config)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Fix", str(exc))
            return
        QtWidgets.QMessageBox.information(self, "Fix", f"{fixed} noeud(s) corrige(s).")
        self._on_run_all()  # re-check

    def _on_select_errors(self):
        nodes = []
        for data in self._report.values():
            if data["status"] == checks.ERROR:
                nodes.extend(data["nodes"])
        if not nodes:
            return
        try:
            import maya.cmds as cmds  # type: ignore
            cmds.select(nodes, replace=True)
        except Exception:  # noqa: BLE001
            pass

    def _on_export(self):
        if not self._report:
            QtWidgets.QMessageBox.information(self, "Export", "Lance d'abord Run All Checks.")
            return
        path, flt = QtWidgets.QFileDialog.getSaveFileName(
            self, "Exporter le rapport", "naming_report.json",
            "JSON (*.json);;Texte (*.txt)")
        if not path:
            return
        if path.endswith(".txt"):
            lines = [checks.summarize(self._report), ""]
            from ..core import maya_utils
            for name, data in self._report.items():
                lines.append(f"[{data['status'].upper()}] {data.get('label', name)} - {data['message']}")
                for node in data["nodes"]:
                    lines.append(f"    {maya_utils.short_name(node)}")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
        else:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._report, fh, indent=4, ensure_ascii=False)
        QtWidgets.QMessageBox.information(self, "Export", f"Rapport ecrit:\n{path}")
