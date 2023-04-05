"""Specifies the Settings Window
"""
import os

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6 import uic


class SettingsWindow(QtWidgets.QWidget):
    """The Settings Widget
    """

    def __init__(self, handler, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uic.loadUi(os.path.join(os.path.dirname(__file__), "ui/settings.ui"), self)
        self.setWindowTitle("Settings")

        self.handler = handler

        self.profileChooser.currentTextChanged.connect(self.change_profile)

        self.get_profile_list()

        self.profileChooser.setCurrentText(self.handler.current_profile)

        self.ApplyButton.pressed.connect(self.apply_settings)
        self.CancelButton.pressed.connect(self.close)
        self.addProfileButton.pressed.connect(self.add_profile)
        self.addIncExc.pressed.connect(self.add_include_exclude)

        self.buttonGroupINcExc = QtWidgets.QButtonGroup()
        self.buttonGroupINcExc.setExclusive(True)
        self.buttonGroupINcExc.addButton(self.incToggle)
        self.buttonGroupINcExc.addButton(self.excToggle)

        toggle_width = max(self.incToggle.width(), self.excToggle.width())
        self.incToggle.setMinimumWidth(toggle_width)
        self.excToggle.setMinimumWidth(toggle_width)

        self.listWidgetExclude.setDragDropMode(
            QtWidgets.QAbstractItemView.DragDropMode.InternalMove
            )

        self.resize(self.screen().availableSize() * 0.5)

    applied = QtCore.pyqtSignal()

    def get_profile_list(self):
        """Get a list of available profiles and add them to combo box
        """
        self.profileChooser.clear()

        profile_list = self.handler.config["Profiles"].keys()

        self.profileChooser.addItems(profile_list)

    def get_cfg_values(self, profile):
        """Fills the Form with the current config values

        :param profile: Name of the Profile
        :type profile: str
        """
        profile_d = self.handler.config["Profiles"][profile]

        def clear_and_set_le(target, key):

            target.clear()
            if key in profile_d.keys():
                target.setText(profile_d[key])

        clear_and_set_le(self.lineEditTarget, "Target")
        clear_and_set_le(self.lineEditSource, "Source")
        clear_and_set_le(self.lineEditFingerprint, "encrypt-key")
        clear_and_set_le(self.lineEditSignFingerprint, "encrypt-sign-key")

        self.checkBoxEncrypt.setCheckState(Qt.CheckState.Checked)
        if "encrypt" in profile_d.keys() and profile_d["encrypt"] is False:
            self.checkBoxEncrypt.setCheckState(Qt.CheckState.Unchecked)

        self.checkBoxAgent.setCheckState(Qt.CheckState.Unchecked)
        if "use-agent" in profile_d.keys() and profile_d["use-agent"]:
            self.checkBoxAgent.setCheckState(Qt.CheckState.Checked)

        self.listWidgetExclude.clear()

        if "selection-flags" in profile_d.keys():
            for flag in profile_d["selection-flags"]:
                self.listWidgetExclude.addItem(
                    self.make_editable_list_item(flag)
                )

    def change_profile(self, text):
        """Triggered if profile is changed

        :param text: New profile name
        :type text: str
        """

        if text:
            self.get_cfg_values(text)

    def add_profile(self):
        """Add a new profile to the list
        """
        text, ok = QtWidgets.QInputDialog.getText(
                        self,
                        "Choose a Profile Name",
                        "Enter Name:")

        if ok:
            if text in self.handler.config["Profiles"].keys():
                # TODO: Show Message in GUI
                print("Profile already exists")
                return

            self.handler.config["Profiles"][text] = {}
        else:
            return

        self.get_profile_list()
        self.profileChooser.setCurrentText(text)

    def make_editable_list_item(self, text) -> QtWidgets.QListWidgetItem:
        item = QtWidgets.QListWidgetItem(text)
        item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
        return item

    def add_include_exclude(self) -> None:
        incexctype = None
        if self.incToggle.isChecked():
            incexctype = "--include "
        else:
            incexctype = "--exclude "

        item = self.make_editable_list_item(incexctype + self.lineEditIncExc.text())
        self.listWidgetExclude.addItem(item)

    def apply_settings(self):
        """Apply the settings to the handler-config.
        """

        profile_name = self.profileChooser.currentText()

        tmp = self.handler.config["Profiles"][profile_name]
        tmp["Target"] = self.lineEditTarget.text()
        tmp["Source"] = self.lineEditSource.text()
        tmp["encrypt-key"] = self.lineEditFingerprint.text()
        tmp["encrypt-sign-key"] = self.lineEditSignFingerprint.text()
        tmp["use-agent"] = self.checkBoxAgent.isChecked()
        tmp["encrypt"] = self.checkBoxEncrypt.isChecked()

        tmp["selection-flags"] = []
        for i in range(self.listWidgetExclude.count()):
            tmp["selection-flags"].append(
                self.listWidgetExclude.item(i).text()
                )

        self.handler.save_config()

        self.applied.emit()
