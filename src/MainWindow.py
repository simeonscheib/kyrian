"""Main Window of Kyrian GUI
"""
import os

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6 import uic

from duplicity import config

from kyrian.settings_window import SettingsWindow
from kyrian.actionHandler import actionHandler
from kyrian.workers import (BackupWorker,
                           TreeWorker,
                           RecoveryWorker)


class MainWindow(QtWidgets.QMainWindow):
    """MainWindow class
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uic.loadUi(os.path.join(os.path.dirname(__file__), "ui/mw.ui"), self)
        self.setWindowTitle("Kyrian")

        # New actionHandler
        self.a = actionHandler(os.path.expanduser("~/.config/kyrian/"))

        # Setup other windows
        self.settingsWindow = SettingsWindow(self.a)

        # Config for MainWindow
        self.config = {}
        self.config["highlight_diffs"] = False
        self.config["build_tree"] = False

        # Setup workers
        self.backup_worker = BackupWorker(self.a)
        self.tree_worker = TreeWorker(self.a)
        self.recovery_worker = RecoveryWorker(self.a)

        self.make_backup_list()

        self.listWidget.currentItemChanged.connect(self.build_tree)
        self.listWidget.setCurrentRow(0)

        # Setup treeMenu
        self.treeMenu = QtWidgets.QMenu(self)
        self.recovAction = QtGui.QAction("Recover File")
        self.treeMenu.addAction(self.recovAction)
        self.recovAction.triggered.connect(self.recoverSelectedFiles)

        self.treeWidget.customContextMenuRequested.connect(
                            self.contextMenuTree)

        # Setup tree
        self.treeWidget.setProperty("class", "treeclass")
        self.treeWidget.setColumnCount(2)
        self.treeWidget.setHeaderLabels(["Name", "Date"])
        self.treeWidget.setColumnWidth(0, 400)

        # Connect signals
        self.actionSettings.setIcon(QtGui.QIcon.fromTheme("preferences"))
        self.actionSettings.triggered.connect(self.open_settings)

        self.actionBackup.triggered.connect(self.start_backup)
        self.actionRestore.triggered.connect(self.restore_snap)

        self.settingsWindow.applied.connect(self.make_backup_list)

        self.actionHighlight_Differences.toggled.connect(self.set_hl)
        self.actionData_Tree.toggled.connect(self.set_tree)

        self.resize(self.screen().availableSize() * 0.7)

    def make_backup_list(self) -> None:
        """Add all available backup chains to list
        """
        chain_d = self.a.get_chains()

        for i in reversed(sorted(chain_d)):
            self.listWidget.addItem(" ".join([chain_d[i][1], chain_d[i][0]]))
            last_item = self.listWidget.item(self.listWidget.count()-1)
            last_item.setData(Qt.ItemDataRole.UserRole, i)

    def open_settings(self) -> None:
        """Show the settings window
        """
        self.settingsWindow.show()

    def disable_buttons(self, b_disable: bool = True) -> None:
        """Disable buttons

        :param b_disable: disable?, defaults to True
        :type b_disable: bool, optional
        """
        self.actionBackup.setEnabled(not b_disable)
        self.actionRestore.setEnabled(not b_disable)
        self.recovAction.setEnabled(not b_disable)

    def start_backup(self) -> None:
        """Start a new backup in a seperate thread
        """

        self.disable_buttons(True)

        if (self.backup_worker.isRunning()
            or self.recovery_worker.isRunning()):

            return

        self.backup_worker.safe = False

        if not self.tree_worker.safe:
            self.tree_worker.wait()

        self.backup_worker.backupReady.connect(self.post_backup)
        self.backup_worker.start()

    def post_backup(self) -> None:
        """Remake the chain list after backup and enable buttons
        """
        self.backup_worker.backupReady.disconnect()
        chain_d = self.a.get_chains()
        key = sorted(chain_d.keys())[-1]
            
        self.listWidget.insertItem(0,
                " ".join([chain_d[key][1], chain_d[key][0]])
                )
        self.listWidget.setCurrentRow(0)
        self.disable_buttons(False)

    def contextMenuTree(self, i) -> None:
        """Open context Menu on tree item

        :param i: Coordinates in the reference frame of the tree
        :type i: QPoint
        """
        self.treeMenu.exec(self.treeWidget.mapToGlobal(i))

    def recoverSelectedFiles(self) -> None:
        """Recover a selcted file or folder from the data-tree
        """

        # Disable buttons to prevent two duplicity instances from running
        self.disable_buttons(True)

        # Abort if there is already a worker running
        if (self.backup_worker.isRunning()
            or self.recovery_worker.isRunning()):

            return

        # Get the selected item from the tree
        sel_list = self.treeWidget.selectedItems()

        if sel_list == []:
            return

        # Signal that worker is working on the target dir
        self.recovery_worker.safe = False

        # Get data of the item
        paths = sel_list[0].data(0, Qt.ItemDataRole.UserRole)
        ftype = sel_list[0].data(1, Qt.ItemDataRole.UserRole)
        name = sel_list[0].text(0)

        # Get the timestamp of the selected backup
        item = self.listWidget.selectedItems()[0]
        time = item.data(Qt.ItemDataRole.UserRole)

        # FileDialog to select local path
        fd = QtWidgets.QFileDialog()

        fd.setFileMode(QtWidgets.QFileDialog.FileMode.Directory)

        if ftype == "dir":
            r_path, rest = fd.getSaveFileName(self,
                                "Select Destination",
                                name,
                                "",
                                "",
                                options=QtWidgets.QFileDialog.Option.ShowDirsOnly
                                )
        else:
            r_path, rest = fd.getSaveFileName(self,
                                "Select Destination",
                                name,
                                "",
                                "")

            if r_path and QtCore.QFile(r_path).exists():
                config.force = True

        if r_path:
            # Wait for other workers to finnish
            # TODO: Wait only until safe not finnished
            if not self.tree_worker.safe:
                self.tree_worker.wait()

            if not self.backup_worker.safe:
                self.backup_worker.wait()

            # Set params of the recovery worker
            self.recovery_worker.time = time
            self.recovery_worker.dest = r_path
            self.recovery_worker.file = paths

            self.recovery_worker.recoveryReady.connect(self.post_file_recovery)
            self.recovery_worker.start()

    def restore_snap(self) -> None:
        """Restores whole snapshot
        """
        # Disable buttons to prevent two duplicity instances from running
        self.disable_buttons(True)

        # Abort if there is already a worker running
        if (self.backup_worker.isRunning()
            or self.recovery_worker.isRunning()):

            return

        # Signal that worker is working on the target dir
        self.recovery_worker.safe = False

        # Get the timestamp of the selected backup
        item = self.listWidget.selectedItems()[0]
        time = item.data(Qt.ItemDataRole.UserRole)

        # FileDialog to select local path
        fd = QtWidgets.QFileDialog()

        fd.setFileMode(QtWidgets.QFileDialog.FileMode.Directory)

        r_path = fd.getExistingDirectory(self,
                        "Select Destination",
                        os.path.expanduser("~"),
                        QtWidgets.QFileDialog.Option.ShowDirsOnly
                        )

        if r_path:

            # Ask permission to force restore on non empty dir
            if (QtCore.QDir(r_path).exists()
                and not QtCore.QDir(r_path).isEmpty()):

                msgbox_r = QtWidgets.QMessageBox.warning(self,
                                "Folder not empty",
                                ("The selected Folder is not empty\n"
                                "Do you want to force recovery anyways?"),
                                (
                                    QtWidgets.QMessageBox.StandardButton.Abort |
                                    QtWidgets.QMessageBox.StandardButton.Yes)
                                )

                if msgbox_r != QtWidgets.QMessageBox.StandardButton.Yes:
                    self.disable_buttons(False)
                    self.recovery_worker.safe = True
                else:
                    config.force = True

            # Wait for other workers to finnish
            # TODO: Wait only until safe not finnished            
            if not self.tree_worker.safe:
                self.tree_worker.wait()

            if not self.backup_worker.safe:
                self.backup_worker.wait()

            # Set params of the recovery worker
            self.recovery_worker.time = time
            self.recovery_worker.dest = r_path
            self.recovery_worker.file = None

            self.recovery_worker.recoveryReady.connect(self.post_file_recovery)
            self.recovery_worker.start()

    def post_file_recovery(self) -> None:
        """After recovery is finnished clean up and enable buttons
        """
        self.recovery_worker.recoveryReady.disconnect()
        config.force = False
        self.disable_buttons(False)

    def build_tree(self,
                   item: QtWidgets.QTreeWidgetItem,
                   prev: QtWidgets.QTreeWidgetItem) -> None:
        """Build the data tree of the backup contents
        """
        if not self.backup_worker.safe:
            return

        if not self.recovery_worker.safe:
            return

        # Make sure there is a selection
        if self.listWidget.selectedItems() == []:
            self.treeWidget.clear()
            return

        if self.tree_worker.isRunning():
            # self.tree_worker.treeReady.disconnect()
            
            self.tree_worker.requestInterruption()
            self.tree_worker.wait(5000)
            if self.tree_worker.isRunning():
                print("terminating")
                self.tree_worker.terminate()
                self.tree_worker.wait()

        if prev:
            if not prev.data(Qt.ItemDataRole.UserRole+1):
                prev.setData(
                    Qt.ItemDataRole.UserRole+1,
                    QtWidgets.QTreeWidgetItem()
                    )

            if not prev.data(Qt.ItemDataRole.UserRole+2):
                prev.setData(
                    Qt.ItemDataRole.UserRole+2,
                    self.tree_worker.files_l
                    )
            
            if prev.data(Qt.ItemDataRole.UserRole+3) == None:
                prev.setData(
                    Qt.ItemDataRole.UserRole+3,
                    self.tree_worker.diff_l
                    )
                
            prev.data(Qt.ItemDataRole.UserRole+1).addChildren(
                    self.treeWidget.invisibleRootItem().takeChildren()
                )

            if item.data(Qt.ItemDataRole.UserRole+1):
                self.treeWidget.invisibleRootItem().addChildren(
                        item.data(Qt.ItemDataRole.UserRole+1).takeChildren()
                    )
        else:
            item.setData(Qt.ItemDataRole.UserRole+2, self.tree_worker.files_l)
            item.setData(Qt.ItemDataRole.UserRole+3, self.tree_worker.diff_l)

        self.tree_worker.files_l = item.data(Qt.ItemDataRole.UserRole+2)
        self.tree_worker.diff_l = item.data(Qt.ItemDataRole.UserRole+3)

        if not self.config["build_tree"]:
            return

        time = item.data(Qt.ItemDataRole.UserRole)

        self.tree_worker.time = time
        self.tree_worker.highlight_diffs = self.config["highlight_diffs"]

        self.tree_worker.root = self.treeWidget.invisibleRootItem()

        self.tree_worker.treeReady.connect(self.post_tree)

        self.tree_worker.safe = False
        self.tree_worker.start()

    def post_tree(self) -> None:
        """After building the tree cleanup
        """
        self.tree_worker.treeReady.disconnect()

    def set_hl(self, b: bool) -> None:
        """Toggle the highlight config option

        :param b: check state of action
        :type b: bool
        """
        self.config["highlight_diffs"] = b
        self.build_tree(self.listWidget.selectedItems()[0], None)

    def set_tree(self, b: bool) -> None:
        """Toggle the tree creation config option

        :param b: check state of action
        :type b: bool
        """
        self.config["build_tree"] = b
        if b:
            self.build_tree(self.listWidget.selectedItems()[0], None)

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:

        if self.tree_worker.isRunning():
            # self.tree_worker.treeReady.disconnect()
            
            self.tree_worker.requestInterruption()
            self.tree_worker.wait(5000)
            if self.tree_worker.isRunning():
                print("terminating")
                self.tree_worker.terminate()
                self.tree_worker.wait()

        a0.accept()

        return super().closeEvent(a0)
