"""Worker Threads to call duplicity
"""
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from duplicity import dup_time
from duplicity import path
from duplicity import config


class BackupWorker(QtCore.QThread):
    """Make Backups in seperate thread
    """

    def __init__(self, handler, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.handler = handler

        self.safe = True

    backupReady = QtCore.pyqtSignal()

    def run(self):
        self.safe = False
        self.handler.make_backup()
        self.safe = True
        self.backupReady.emit()


class RecoveryWorker(QtCore.QThread):
    """Make Recovery in seperate thread
    """

    def __init__(self, handler, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.handler = handler

        self.safe = True

        self.time = None

        self.dest = None

        self.file = None

    recoveryReady = QtCore.pyqtSignal()

    def run(self):

        local_path = path.Path(path.Path(self.dest).get_canonical())
        if ((local_path.exists() and not local_path.isemptydir())
            and not config.force):

            print("File already exists")
            return
        else:
            self.safe = False
            self.handler.recover_files(self.dest,
                                       file=self.file,
                                       time=self.time)
            self.safe = True

            self.time = None
            self.dest = None
            self.file = None
            self.recoveryReady.emit()
            

class TreeWorker(QtCore.QThread):
    """Build the tree in a seperate thread
    """

    file_icon_p = QtWidgets.QFileIconProvider()

    def __init__(self, handler, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.handler = handler

        # List of differing files and direcories
        self.diff_l = None

        self.time = None
        self.highlight_diffs = False

        # False if duplicity is busy
        self.safe = True

        # Root of the tree
        self.root = None

    # Signal that the tree is ready
    treeReady = QtCore.pyqtSignal()

    def make_tree_item(self, dat, parent=None):
        """Add tree elements and add them to their parent

        :param dat: data to add a new node
        :type dat: tuple
        :param parent: The parent tree node, defaults to None
        :type parent: QTreeWidgetItem, optional
        :raises IndexError: 
        :raises IndexError: 
        :return: Tree Root Node if parent is not set
        :rtype: QTreeWidgetItem
        """
        # Timestamp of the node
        time = dat[0]

        # Type of the node
        ftype = str(dat[2])

        # Path relative to backup root
        path_s = dat[1].decode("utf-8")

        # Elements of the path string
        path_elements = path_s.split("/")

        # New tree item without parent
        if not parent:
            if len(path_elements) == 1:
                tmp = QtWidgets.QTreeWidgetItem([
                                                path_elements[0], 
                                                dup_time.timetopretty(time)
                                                ])
                tmp.setIcon(0,
                            self.file_icon_p.icon(
                                QtWidgets.QFileIconProvider.IconType.Folder
                                )
                            )
                return tmp
            else:
                raise IndexError("Path too long to build root")

        # True if file differs from source
        diff = False

        # Check if file is different
        if self.highlight_diffs and path_s in self.diff_l.keys():
            diff = True

        # Iterate path
        for i in path_elements:

            # Search existing folders
            found = False
            for j in range(parent.childCount()):
                if parent.child(j).data(0, 0) == i:
                    parent = parent.child(j)
                    found = True
                    break

            if not found:
                if path_elements[-1] != i:
                    raise IndexError("Path broken")

                tmp = QtWidgets.QTreeWidgetItem([i, dup_time.timetopretty(time)])
                tmp.setData(0, Qt.ItemDataRole.UserRole, path_s)
                tmp.setData(1, Qt.ItemDataRole.UserRole, ftype)

                if ftype == "dir":
                    tmp.setIcon(0,
                                self.file_icon_p.icon(
                                    QtWidgets.QFileIconProvider.IconType.Folder
                                    )
                                )
                elif ftype == "reg":
                    tmp.setIcon(0,
                                self.file_icon_p.icon(
                                    QtWidgets.QFileIconProvider.IconType.File
                                    )
                                )

                if diff:
                    tmp.setForeground(0, QtGui.QBrush(QtGui.QColor(255, 0, 0)))
                    tmp.setData(0,
                                Qt.ItemDataRole.ForegroundRole,
                                QtGui.QBrush(QtGui.QColor(255, 0, 0))
                                )

                parent.addChild(tmp)
                break

    def run(self):
        """Build the data-tree 
        """
        if not self.time:
            self.treeReady.emit(None)

        self.safe = False
        f = self.handler.get_files(time=self.time)

        if self.highlight_diffs:
            self.diff_l = self.handler.get_diff(time=self.time)
        self.safe = True

        # tl = self.make_tree_item(f[0])

        for i in f[1:]:
            self.make_tree_item(i, self.root)

        self.root = None

        self.treeReady.emit()
