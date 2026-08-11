"""Main dockable window: QTabWidget with Renamer / Validator / Config tabs."""

from __future__ import annotations

import json
import logging

from PySide6 import QtCore, QtWidgets

from maya.app.general.mayaMixin import MayaQWidgetDockableMixin  # type: ignore

from ..core import config as config_mod
from .renamer_tab import RenamerTab
from .validator_tab import ValidatorTab

log = logging.getLogger("namingTool")


class ScopeSelector(QtWidgets.QWidget):
    """Selection / Hierarchy / Scene radio group, shared by the tabs."""

    changed = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QtWidgets.QLabel("Portee:"))
        self.buttons = {}
        self._group = QtWidgets.QButtonGroup(self)
        for key, label in (("selection", "Selection"),
                           ("hierarchy", "Hierarchie"),
                           ("scene", "Scene")):
            rb = QtWidgets.QRadioButton(label)
            rb.toggled.connect(lambda on, k=key: on and self.changed.emit(k))
            self._group.addButton(rb)
            self.buttons[key] = rb
            layout.addWidget(rb)
        self.buttons["selection"].setChecked(True)
        layout.addStretch(1)

    def scope(self) -> str:
        for key, rb in self.buttons.items():
            if rb.isChecked():
                return key
        return "selection"


class NamingToolWindow(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    def __init__(self, config_path=None, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("namingToolWindow")
        self.config_path = config_path
        self.config = config_mod.load_config(config_path)
        self.setWindowTitle("Naming Tool - v%s" % self.config.get("version", "1.0"))
        self.setMinimumSize(560, 620)
        self._build_ui()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)

        self.scope = ScopeSelector()
        root.addWidget(self.scope)

        self.tabs = QtWidgets.QTabWidget()
        self.renamer_tab = RenamerTab(self)
        self.validator_tab = ValidatorTab(self)
        self.config_tab = self._build_config_tab()
        self.tabs.addTab(self.renamer_tab, "Renamer")
        self.tabs.addTab(self.validator_tab, "Validator")
        self.tabs.addTab(self.config_tab, "Config")
        root.addWidget(self.tabs, 1)

    # -- Config tab ----------------------------------------------------- #
    def _build_config_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        info = QtWidgets.QLabel(
            "Convention active. Modifiez le JSON puis 'Recharger'. "
            "Variable d'env NAMINGTOOL_CONFIG pour une config partagee equipe."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#999999;")
        layout.addWidget(info)

        self.config_view = QtWidgets.QPlainTextEdit()
        self.config_view.setReadOnly(True)
        self.config_view.setStyleSheet("font-family: Consolas, monospace;")
        self.config_view.setPlainText(json.dumps(self.config, indent=4, ensure_ascii=False))
        layout.addWidget(self.config_view, 1)

        btns = QtWidgets.QHBoxLayout()
        reload_btn = QtWidgets.QPushButton("Recharger la config")
        reload_btn.clicked.connect(self._reload_config)
        btns.addWidget(reload_btn)
        btns.addStretch(1)
        layout.addLayout(btns)
        return w

    def _reload_config(self):
        config_mod.clear_cache()
        self.config = config_mod.load_config(self.config_path)
        self.config_view.setPlainText(json.dumps(self.config, indent=4, ensure_ascii=False))
        # rebuild tabs that cache presets from config
        self.renamer_tab.rebuild_presets(self.config)
        QtWidgets.QMessageBox.information(self, "Config", "Configuration rechargee.")

    # -- shared ---------------------------------------------------------- #
    def current_scope(self) -> str:
        return self.scope.scope()

    def show_dockable(self):
        self.show(dockable=True, area="right", floating=True)
