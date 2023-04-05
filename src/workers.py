"""Worker Threads to call duplicity
"""
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from duplicity import dup_time
from duplicity import path
from duplicity import config
from duplicity import commandline


class BackupWorker(QtCore.QThread):
    """Make Backups in seperate thread
    """

    def __init__(self, handler, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.handler = handler

        self.safe = True

        self.sys_exit = None

    backupReady = QtCore.pyqtSignal()

    def run(self) -> None:
        # Clear select options !!!
        commandline.select_opts = []
        self.safe = False
        try:
            self.handler.make_backup()
        except SystemExit as e:
            self.sys_exit = e.code
            self.safe = True
            return
        except Exception as e:
            raise e
        self.safe = True
        self.backupReady.emit()


class RecoveryWorker(QtCore.QThread):
    """Make Recovery in seperate thread
    """

    def __init__(self, handler, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.handler = handler

        self.safe = True

        self.time = None

        self.dest = None

        self.file = None

    recoveryReady = QtCore.pyqtSignal()

    def run(self) -> None:

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

    def __init__(self, handler, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.handler = handler

        # List of files and direcories
        self.files_l = None

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

        # Iterate path
        for i in path_elements:

            # Search existing folders
            found = False
            #for j in range(parent.childCount()):
            #    if parent.child(j).data(0, 0) == i:
            #        parent = parent.child(j)
            #        found = True
            #        break

            # Assuming the generator sorts files correctly
            # Only check the last child element
            cc = parent.childCount()
            if cc > 0 and parent.child(cc-1).data(0, 0) == i:
                parent = parent.child(cc-1)
                found = True

            if not found:
                if path_elements[-1] != i:
                    raise IndexError("Path broken " + i + " " + path_elements[-1] + " " + path_s)

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

                parent.addChild(tmp)
                break

    def setItemColor(self,
                     item: QtWidgets.QTreeWidgetItem,
                     color: QtGui.QColor) -> None:
        """Set the color of a tree item

        :param item: The item
        :type item: QtWidgets.QTreeWidgetItem
        :param color: The color
        :type color: QtGui.QColor
        """
        item.setForeground(0, QtGui.QBrush(color))
        item.setData(0,
                    Qt.ItemDataRole.ForegroundRole,
                    QtGui.QBrush(color)
                    )

    def highlight_leaf(self, path_s, ftype) -> None:
        """Highlight every element of a relative path in the tree

        :param path_s: path
        :param ftype: File type
        """
        # Elements of the path string
        path_elements = path_s.split("/")

        parent = self.root

        # Iterate path
        for i in path_elements:
            for j in range(parent.childCount()):
                if parent.child(j).data(0, 0) == i:
                    parent = parent.child(j)
                    self.setItemColor(parent, QtGui.QColor(255, 0, 0))
                    break

    def cleanup(self) -> None:
        """Clean up afterwards
        """
        self.root = None

        self.treeReady.emit()

    def run(self) -> None:
        """Build the data-tree 
        """
        if not self.time:
            self.treeReady.emit()

        self.safe = False
        if not self.files_l:
            self.files_l = self.handler.get_files(time=self.time)

            # Skip "."
            next(self.files_l)

        self.safe = True

        if not self.files_l:
            self.cleanup()
            return

        for i in self.files_l:
            if i.difftype != u"deleted":
                self.make_tree_item(
                    (
                        i.getmtime(),
                        i.get_relative_path(),
                        i.type),
                    self.root)

            if self.isInterruptionRequested():
                self.cleanup()
                return
        
        if self.highlight_diffs and self.diff_l == None:
            self.safe = False
            self.diff_l = self.handler.get_diff(time=self.time)
            self.safe = True

        if self.highlight_diffs and not self.isInterruptionRequested():
            for i in self.diff_l:
                self.highlight_leaf(i, self.diff_l[i])

                if self.isInterruptionRequested():
                    self.cleanup()
                    return


