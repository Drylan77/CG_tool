"""PySide6 UI for the CG asset renaming tool (Maya 2025.3).

The window is generated dynamically from the naming convention JSON, so adding
or reordering tokens in the config automatically updates the interface.
"""

from __future__ import annotations

import os
from typing import Dict, List

from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import wrapInstance

import maya.OpenMayaUI as omui  # type: ignore

from .naming_convention import NamingConvention, DEFAULT_CONFIG_PATH
from .renamer import Renamer, RenameEntry, CheckEntry
from . import maya_utils


WINDOW_OBJECT_NAME = "cgAssetRenamerWindow"


def maya_main_window() -> QtWidgets.QWidget:
    """Return Maya's main window as a QWidget to parent the tool to it."""
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget)


class TokenField(QtWidgets.QWidget):
    """A labelled input row for a single token (line edit or combo box)."""

    changed = QtCore.Signal()

    def __init__(self, token, parent=None):
        super().__init__(parent)
        self.token = token
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        label_txt = token.label + (" *" if token.required else "")
        self.label = QtWidgets.QLabel(label_txt)
        self.label.setMinimumWidth(150)
        if token.required:
            self.label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.label)

        if token.type == "choice":
            self.input = QtWidgets.QComboBox()
            for item in token.values:
                self.input.addItem(item["label"], item["value"])
            # select the default value
            idx = self.input.findData(token.default)
            if idx >= 0:
                self.input.setCurrentIndex(idx)
            self.input.currentIndexChanged.connect(self.changed)
        else:
            self.input = QtWidgets.QLineEdit()
            self.input.setText(token.default)
            self.input.setPlaceholderText(token.hint or token.label)
            self.input.textChanged.connect(self.changed)
        layout.addWidget(self.input, 1)

        if token.hint:
            self.setToolTip(token.hint)
            self.label.setToolTip(token.hint)

    def value(self) -> str:
        if isinstance(self.input, QtWidgets.QComboBox):
            return self.input.currentData()
        return self.input.text()


class RenamerWindow(QtWidgets.QDialog):
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH, parent=None):
        super().__init__(parent or maya_main_window())
        self.convention = NamingConvention.from_file(config_path)
        self.renamer = Renamer(self.convention)
        self.fields: Dict[str, TokenField] = {}
        self._last_entries: List[CheckEntry] = []

        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle(f"CG Asset Renamer  -  {self.convention.name} v{self.convention.version}")
        self.setMinimumWidth(520)
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)

        self._build_ui()
        self._refresh_preview()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(8)

        # -- header ----------------------------------------------------- #
        header = QtWidgets.QLabel(self.convention.description or self.convention.name)
        header.setWordWrap(True)
        header.setStyleSheet("color: #aaaaaa;")
        root.addWidget(header)

        # -- token fields ----------------------------------------------- #
        form_box = QtWidgets.QGroupBox("Parametres du nom")
        form_layout = QtWidgets.QVBoxLayout(form_box)
        for tok in self.convention.tokens:
            fld = TokenField(tok)
            fld.changed.connect(self._refresh_preview)
            self.fields[tok.key] = fld
            form_layout.addWidget(fld)
        root.addWidget(form_box)

        # -- preview ---------------------------------------------------- #
        prev_box = QtWidgets.QGroupBox("Apercu")
        prev_layout = QtWidgets.QVBoxLayout(prev_box)
        self.preview_label = QtWidgets.QLabel("-")
        self.preview_label.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 14px; color: #7fd37f;"
            " padding: 6px; background: #2b2b2b; border-radius: 4px;"
        )
        self.preview_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        prev_layout.addWidget(self.preview_label)
        self.selection_info = QtWidgets.QLabel("")
        self.selection_info.setStyleSheet("color: #888888; font-size: 11px;")
        prev_layout.addWidget(self.selection_info)
        root.addWidget(prev_box)

        # -- options ---------------------------------------------------- #
        self.auto_type_cb = QtWidgets.QCheckBox("Auto-detect Type depuis le node (mesh->GEO, curve->CRV...)")
        self.auto_type_cb.setToolTip(
            "Ignore le champ Type et le deduit de la forme de chaque objet."
        )
        self.auto_type_cb.stateChanged.connect(self._on_auto_type_toggled)
        root.addWidget(self.auto_type_cb)

        # -- rename buttons --------------------------------------------- #
        btn_row = QtWidgets.QHBoxLayout()
        self.refresh_btn = QtWidgets.QPushButton("Refresh selection")
        self.refresh_btn.clicked.connect(self._refresh_preview)
        self.rename_btn = QtWidgets.QPushButton("RENAME selection")
        self.rename_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.rename_btn.clicked.connect(self._on_rename)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.rename_btn, 1)
        root.addLayout(btn_row)

        # -- checker ---------------------------------------------------- #
        check_box = QtWidgets.QGroupBox("Verification des noms (Check)")
        check_layout = QtWidgets.QVBoxLayout(check_box)
        check_btn_row = QtWidgets.QHBoxLayout()
        self.check_sel_btn = QtWidgets.QPushButton("Check selection")
        self.check_sel_btn.clicked.connect(lambda: self._on_check(scope="selection"))
        self.check_scene_btn = QtWidgets.QPushButton("Check scene")
        self.check_scene_btn.clicked.connect(lambda: self._on_check(scope="scene"))
        self.autofix_btn = QtWidgets.QPushButton("Auto-fix selection")
        self.autofix_btn.setToolTip(
            "Renomme les objets selectionnes non conformes vers le nom valide le plus proche."
        )
        self.autofix_btn.clicked.connect(self._on_autofix)
        self.export_btn = QtWidgets.QPushButton("Export CSV")
        self.export_btn.setToolTip("Exporte le dernier rapport de verification en CSV.")
        self.export_btn.clicked.connect(self._on_export)
        check_btn_row.addWidget(self.check_sel_btn)
        check_btn_row.addWidget(self.check_scene_btn)
        check_btn_row.addWidget(self.autofix_btn)
        check_btn_row.addWidget(self.export_btn)
        check_layout.addLayout(check_btn_row)

        self.result_tree = QtWidgets.QTreeWidget()
        self.result_tree.setColumnCount(3)
        self.result_tree.setHeaderLabels(["Name", "Status", "Details"])
        self.result_tree.setRootIsDecorated(False)
        self.result_tree.setAlternatingRowColors(True)
        self.result_tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.result_tree.header().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        self.result_tree.itemDoubleClicked.connect(self._on_result_double_clicked)
        check_layout.addWidget(self.result_tree)

        self.summary_label = QtWidgets.QLabel("")
        self.summary_label.setStyleSheet("font-size: 11px;")
        check_layout.addWidget(self.summary_label)
        root.addWidget(check_box, 1)

    # ------------------------------------------------------------------ #
    # Slots / logic
    # ------------------------------------------------------------------ #
    def _current_values(self) -> Dict[str, str]:
        return {key: fld.value() for key, fld in self.fields.items()}

    def _selection_count(self) -> int:
        try:
            return len(maya_utils.get_selection())
        except Exception:  # noqa: BLE001
            return 0

    def _on_auto_type_toggled(self) -> None:
        """Grey out the Type field when auto-detection is enabled."""
        auto = self.auto_type_cb.isChecked()
        type_field = self.fields.get("type")
        if type_field:
            type_field.setEnabled(not auto)
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        values = self._current_values()
        count = max(1, self._selection_count())
        try:
            names = self.renamer.build_preview(values, count=count)
            if count > 1:
                shown = ", ".join(names[:3]) + (" ..." if count > 3 else "")
                self.preview_label.setText(shown)
            else:
                self.preview_label.setText(names[0] if names else "-")
        except ValueError as exc:
            self.preview_label.setText(f"[incomplet] {exc}")

        sel = self._selection_count()
        notes = []
        if sel > 1:
            notes.append("index numerique ajoute automatiquement")
        if self.auto_type_cb.isChecked():
            notes.append("Type auto-detecte par objet (l'apercu montre le champ Type courant)")
        self.selection_info.setText(
            f"{sel} objet(s) selectionne(s)" + ("  -  " + " ; ".join(notes) if notes else "")
        )

    def _on_rename(self) -> None:
        try:
            results = self.renamer.rename_selection(
                self._current_values(),
                auto_detect_type=self.auto_type_cb.isChecked(),
            )
        except (RuntimeError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(self, "Renaming", str(exc))
            return
        self._report_rename(results, title="Renaming")
        self._refresh_preview()

    def _on_autofix(self) -> None:
        try:
            results = self.renamer.autofix_selection(
                auto_detect_type=self.auto_type_cb.isChecked()
            )
        except RuntimeError as exc:
            QtWidgets.QMessageBox.warning(self, "Auto-fix", str(exc))
            return
        self._report_rename(results, title="Auto-fix")
        # refresh the check table on the (now renamed) selection
        try:
            self._populate_results(self.renamer.check_selection())
        except RuntimeError:
            pass

    def _report_rename(self, results, title: str) -> None:
        ok = [r for r in results if r.status == "ok"]
        err = [r for r in results if r.status == "error"]
        skipped = [r for r in results if r.status == "skipped"]
        msg = f"{len(ok)} objet(s) renomme(s)."
        if skipped:
            msg += f"  {len(skipped)} deja conforme(s)."
        if err:
            msg += f"\n{len(err)} erreur(s):\n" + "\n".join(
                f"- {e.old_name}: {e.message}" for e in err
            )
            QtWidgets.QMessageBox.warning(self, title, msg)
        else:
            QtWidgets.QMessageBox.information(self, title, msg)

    def _on_check(self, scope: str) -> None:
        try:
            if scope == "selection":
                entries = self.renamer.check_selection()
            else:
                entries = self.renamer.check_scene()
        except RuntimeError as exc:
            QtWidgets.QMessageBox.warning(self, "Check", str(exc))
            return

        self._populate_results(entries)

    def _on_export(self) -> None:
        if not self._last_entries:
            QtWidgets.QMessageBox.information(
                self, "Export", "Lance d'abord un Check pour generer un rapport."
            )
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Exporter le rapport", "naming_report.csv", "CSV (*.csv)"
        )
        if not path:
            return
        self.renamer.export_report(self._last_entries, path)
        QtWidgets.QMessageBox.information(self, "Export", f"Rapport ecrit:\n{path}")

    def _populate_results(self, entries: List[CheckEntry]) -> None:
        self._last_entries = entries
        self.result_tree.clear()
        ok_count = 0
        for entry in entries:
            if entry.valid:
                ok_count += 1
                status, color, details = "OK", QtGui.QColor("#7fd37f"), "conforme"
            else:
                status, color = "INVALID", QtGui.QColor("#e06c6c")
                details = " | ".join(entry.errors) or "non conforme"
            item = QtWidgets.QTreeWidgetItem([entry.name, status, details])
            item.setForeground(1, QtGui.QBrush(color))
            item.setData(0, QtCore.Qt.UserRole, entry.node)
            self.result_tree.addTopLevelItem(item)

        total = len(entries)
        invalid = total - ok_count
        color = "#7fd37f" if invalid == 0 else "#e0a86c"
        self.summary_label.setText(
            f"<span style='color:{color}'>{ok_count}/{total} conformes, "
            f"{invalid} a corriger.</span>"
        )

    def _on_result_double_clicked(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """Select the corresponding node in Maya on double click."""
        node = item.data(0, QtCore.Qt.UserRole)
        if node and maya_utils.IN_MAYA:
            try:
                import maya.cmds as cmds  # type: ignore
                cmds.select(node, replace=True)
            except Exception:  # noqa: BLE001
                pass


# --------------------------------------------------------------------------- #
# Singleton show helper
# --------------------------------------------------------------------------- #
_window_instance = None


def show(config_path: str = DEFAULT_CONFIG_PATH):
    """Create (or re-show) the renamer window as a Maya-parented singleton."""
    global _window_instance
    try:
        if _window_instance:
            _window_instance.close()
            _window_instance.deleteLater()
    except Exception:  # noqa: BLE001
        pass
    _window_instance = RenamerWindow(config_path=config_path)
    _window_instance.show()
    return _window_instance
