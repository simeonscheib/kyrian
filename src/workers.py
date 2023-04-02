"""Worker Threads to call duplicity
"""
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from duplicity import dup_time
from duplicity import path
from duplicity import config
from duplicity import diffdir
from duplicity import commandline
from duplicity import log
from duplicity import progress

from datetime import datetime, timedelta


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


class ProgressWorker(QtCore.QThread):

    def __init__(self, handler, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.handler = handler

    sendProgress = QtCore.pyqtSignal(int)

    def progress(self):
        u""" Adapted from https://gitlab.com/duplicity/duplicity
        Aproximative and evolving method of computing the progress of upload
        """
        tracker = progress.tracker
        if not tracker.has_collected_evidence():
            return

        current_time = datetime.now()
        if tracker.start_time is None:
            tracker.start_time = current_time
        if tracker.last_time is not None:
            elapsed = (current_time - tracker.last_time)
        else:
            elapsed = timedelta()
        tracker.last_time = current_time

        # Detect (and report) a stallment if no changing data for more than 5 seconds
        if tracker.stall_last_time is None:
            tracker.stall_last_time = current_time
        if (current_time - tracker.stall_last_time).seconds > max(5, 2 * config.progress_rate):
            return (100.0 * tracker.progress_estimation,
                                 tracker.time_estimation, tracker.total_bytecount,
                                 (current_time - tracker.start_time).seconds,
                                 tracker.speed,
                                 True
                                 )

        tracker.nsteps += 1

        u"""
        Compute the ratio of information being written for deltas vs file sizes
        Using Knuth algorithm to estimate approximate upper bound in % of completion
        The progress is estimated on the current bytes written vs the total bytes to
        change as estimated by a first-dry-run. The weight is the ratio of changing
        data (Delta) against the total file sizes. (pessimistic estimation)
        The method computes the upper bound for the progress, when using a sufficient
        large volsize to accomodate and changes, as using a small volsize may inject
        statistical noise.
        """
        changes = diffdir.stats.NewFileSize + diffdir.stats.ChangedFileSize
        total_changes = tracker.total_stats.NewFileSize + tracker.total_stats.ChangedFileSize
        if total_changes == 0 or diffdir.stats.RawDeltaSize == 0:
            return

        # Snapshot current values for progress
        last_progress_estimation = tracker.progress_estimation

        if tracker.is_full:
            # Compute mean ratio of data transfer, assuming 1:1 data density
            tracker.current_estimation = float(tracker.total_bytecount) / float(total_changes)
        else:
            # Compute mean ratio of data transfer, estimating unknown progress
            change_ratio = float(tracker.total_bytecount) / float(diffdir.stats.RawDeltaSize)
            change_delta = change_ratio - tracker.change_mean_ratio
            tracker.change_mean_ratio += change_delta / float(tracker.nsteps)  # mean cumulated ratio
            tracker.change_r_estimation += change_delta * (change_ratio - tracker.change_mean_ratio)
            change_sigma = math.sqrt(math.fabs(tracker.change_r_estimation / float(tracker.nsteps)))

            u"""
            Combine variables for progress estimation
            Fit a smoothed curve that covers the most common data density distributions,
            aiming for a large number of incremental changes.
            The computation is:
                Use 50% confidence interval lower bound during first half of the progression.
                Conversely, use 50% C.I. upper bound during the second half. Scale it to the
                changes/total ratio
            """
            tracker.current_estimation = float(changes) / float(total_changes) * (
                (tracker.change_mean_ratio - 0.67 * change_sigma) * (1.0 - tracker.current_estimation) +
                (tracker.change_mean_ratio + 0.67 * change_sigma) * tracker.current_estimation
            )
            u"""
            In case that we overpassed the 100%, drop the confidence and trust more the mean as the
            sigma may be large.
            """
            if tracker.current_estimation > 1.0:
                tracker.current_estimation = float(changes) / float(total_changes) * (
                    (tracker.change_mean_ratio - 0.33 * change_sigma) * (1.0 - tracker.current_estimation) +
                    (tracker.change_mean_ratio + 0.33 * change_sigma) * tracker.current_estimation
                )
            u"""
            Meh!, if again overpassed the 100%, drop the confidence to 0 and trust only the mean.
            """
            if tracker.current_estimation > 1.0:
                tracker.current_estimation = tracker.change_mean_ratio * float(changes) / float(total_changes)

        u"""
        Lastly, just cap it... nothing else we can do to approximate it better.
        Cap it to 99%, as the remaining 1% to 100% we reserve for the last step
        uploading of signature and manifests
        """
        tracker.progress_estimation = max(0.0, min(tracker.prev_estimation +
                                                (1.0 - tracker.prev_estimation) *
                                                tracker.current_estimation, 0.99))

        u"""
        Estimate the time just as a projection of the remaining time, fit to a
        [(1 - x) / x] curve
        """
        # As sum of timedeltas, so as to avoid clock skew in long runs
        # (adding also microseconds)
        tracker.elapsed_sum += elapsed
        projection = 1.0
        if tracker.progress_estimation > 0:
            projection = (1.0 - tracker.progress_estimation) / tracker.progress_estimation
        tracker.time_estimation = int(projection * float(tracker.elapsed_sum.total_seconds()))

        # Apply values only when monotonic, so the estimates look more consistent to the human eye
        if tracker.progress_estimation < last_progress_estimation:
            tracker.progress_estimation = last_progress_estimation

        u"""
        Compute Exponential Moving Average of speed as bytes/sec of the last 30 probes
        """
        if elapsed.total_seconds() > 0:
            tracker.transfers.append(float(tracker.total_bytecount - tracker.last_total_bytecount) /
                                  float(elapsed.total_seconds()))
        tracker.last_total_bytecount = tracker.total_bytecount
        if len(tracker.transfers) > 30:
            tracker.transfers.popleft()
        tracker.speed = 0.0
        for x in tracker.transfers:
            tracker.speed = 0.3 * x + 0.7 * tracker.speed

        return (100.0 * tracker.progress_estimation,
                             tracker.time_estimation,
                             tracker.total_bytecount,
                             (current_time - tracker.start_time).seconds,
                             tracker.speed,
                             False
                             )

    def run(self):
        """check on progress
        """

        while not self.isInterruptionRequested():
            if progress.tracker:
                data = self.progress()
                self.sendProgress.emit(int(data[0]))

            self.sleep(config.progress_rate)

        self.sendProgress.emit(100)

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
