"""The actionHandler class provides an interface to the
   duplicity backend
"""
import os
import fasteners

from duplicity.dup_main import *
import duplicity.errors

from duplicity import gpg
from duplicity import diffdir
from duplicity import path
from duplicity import log
from duplicity import tempdir
from duplicity import util
from duplicity import commandline
from duplicity import config
from duplicity import dup_time

from kyrian.config_helper import write_config, read_config


def with_tempdir_opts(fn, opts):
    """
    Execute function and guarantee cleanup of tempdir is called

    :param fn: function to execute
    :type fn: callable function
    :param opts: Options to pass to fn
    :type opts: list

    :return: void
    :rtype: void
    """
    try:
        fn(opts)
    finally:
        tempdir.default().cleanup()


class actionHandler():
    """Calls duplicity and returns relevant information
    """
    config_dir = "."

    def __init__(self, cfg_dir=None) -> None:
        """
        Start/end here
        """
        if cfg_dir:
            self.config_dir = cfg_dir

        # per bug https://bugs.launchpad.net/duplicity/+bug/931175
        # duplicity crashes when PYTHONOPTIMIZE is set, so check
        # and refuse to run if it is set.
        if u'PYTHONOPTIMIZE' in os.environ:
            log.FatalError(_(u"""
    PYTHONOPTIMIZE in the environment causes duplicity to fail to
    recognize its own backups.  Please remove PYTHONOPTIMIZE from
    the environment and rerun the backup.

    See https://bugs.launchpad.net/duplicity/+bug/931175
    """), log.ErrorCode.pythonoptimize_set)

        # if python is run setuid, it's only partway set,
        # so make sure to run with euid/egid of root
        if os.geteuid() == 0:
            # make sure uid/gid match euid/egid
            os.setuid(os.geteuid())
            os.setgid(os.getegid())

        # Make the config path in $HOME/.config/kyrian/
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
        
        # Read config of create minimal config
        try:
            self.config = read_config(self.config_dir + "/config.yaml")
        except:
            self.config = {
                            "Profile": "Default",
                            "Profiles": {
                                "Default": {}
                            }
                            }
            self.save_config()

        # Choose default profile, use "Default" or first entry
        if "Profile" in self.config.keys():
            self.current_profile = self.config["Profile"]
        elif "Default" in self.config["Profiles"].keys():
            self.current_profile = "Default"
        else:
            self.current_profile = self.config["Profiles"].keys()[0]

    def save_config(self):
        """Save the config to file
        """
        write_config(self.config, self.config_dir + "/config.yaml")

    def check_config(self, keys):
        """Make sure all necessary keys are given in the configuration

        :param keys: List of keys
        :type keys: list
        :return: Are all keys defined
        :rtype: bool
        """
        for key in keys:
            if key not in self.config["Profiles"][self.current_profile].keys():
                return False
        return True

    def take_action(self, opts):
        """Given a list of duplicity config options run duplicity
        Adapted from https://gitlab.com/duplicity/duplicity

        :param opts: Duplicity options
        :type opts: list
        """

        # set the current time strings
        # (make it available for command line processing)
        dup_time.setcurtime()

        # determine what action we're performing and process command line
        action = commandline.ProcessCommandLine(opts)

        config.lockpath = os.path.join(config.archive_dir_path.name, b"lockfile")
        config.lockfile = fasteners.process_lock.InterProcessLock(config.lockpath)
        log.Debug(_(u"Acquiring lockfile %s") % config.lockpath)
        if not config.lockfile.acquire(blocking=False):
            log.FatalError(
                u"Another duplicity instance is already running with this archive directory\n",
                log.ErrorCode.user_error)
            log.shutdown()
            sys.exit(2)

        try:
            self.do_backup(action)

        finally:
            util.release_lockfile()

    def add_args_from_cfg(self, args):
        """Add general flags to the list of arguments
           depending on configuration

        :param args: List of arguments
        :type args: list
        :return: Modified list of arguments
        :rtype: list
        """

        profile_cfg = self.config["Profiles"][self.current_profile]

        if "use-agent" in profile_cfg.keys():
            args = args + ["--use-agent"]

        if "encrypt" not in profile_cfg.keys() or profile_cfg["encrypt"]:

            if "encrypt-key" in profile_cfg.keys():

                args = args + [
                            "--encrypt-key",
                            profile_cfg["encrypt-key"]
                                ]
        else:
            args = args + ["--no-encryption"]

        return args

    def get_chains(self):
        """Get all available backup chains

        :return: The chains
        :rtype: dict
        """

        if not self.check_config(["Target"]):
            print("No Target specified")
            return {}

        with_tempdir_opts(
            self.take_action,
            [
                "collection-status",
                self.config["Profiles"][self.current_profile]["Target"]
            ]
            )
        commandline.collection_status = None

        return self.chain_dict

    def get_files(self, time=None):
        """Get a list of all files and directories in the backup

        :param time: The timestamp of the backup, defaults to None
        :type time: int, optional
        :return: List of files with type
        :rtype: list
        """
        if self.check_config("Target"):
            print("No Target specified")
            return []

        config.restore_time = time
        with_tempdir_opts(
            self.take_action,
            [
                "list-current-files",
                self.config["Profiles"][self.current_profile]["Target"]
            ])

        commandline.list_current = None

        return self.current_paths

    def get_diff(self, time=None):
        """Get a list of files and directories that differ from 
           the current state

        :param time: Timesamp of the backup, defaults to None
        :type time: int, optional
        :return: List of differing files
        :rtype: list
        """

        if not self.check_config(["Target", "Source"]):
            print("Source and Target unspecified")
            return {}

        config.restore_time = time

        args = ["verify", "--compare-data"]
        args = self.add_args_from_cfg(args)

        args = args + [self.config["Profiles"][self.current_profile]["Target"]]
        args = args + [self.config["Profiles"][self.current_profile]["Source"]]

        with_tempdir_opts(self.take_action, args)
        commandline.verify = None

        return self.diff_f_list

    def recover_files(self, dest, file=None, time=None):
        """Recover a file from the backup

        :param file: Filepath relative in backup
        :type file: str
        :param dest: Destination path
        :type dest: str
        :param time: Timestamp of the backup, defaults to None
        :type time: int, optional
        """
        config.restore_time = time
        args = ["restore"]
        args = self.add_args_from_cfg(args)

        if file:
            args = args + ["--file-to-restore", file]

        args = args + [self.config["Profiles"][self.current_profile]["Target"]]

        args = args + [dest]
        with_tempdir_opts(self.take_action, args)

    def make_backup(self):
        """Make a Snapshot of Source to Target
        """
        args = []
        args = self.add_args_from_cfg(args)

        args = args + [self.config["Profiles"][self.current_profile]["Source"]]
        args = args + [self.config["Profiles"][self.current_profile]["Target"]]

        with_tempdir_opts(self.take_action, args)

    def do_backup(self, action):
        """Adapted from https://gitlab.com/duplicity/duplicity
        """

        # set the current time strings again now that we have time separator
        if config.current_time:
            dup_time.setcurtime(config.current_time)
        else:
            dup_time.setcurtime()

        # log some debugging status info
        log_startup_parms(log.INFO)

        # check for disk space and available file handles
        check_resources(action)

        # get current collection status
        col_stats = dup_collections.CollectionsStatus(config.backend,
                                                      config.archive_dir_path,
                                                      action).set_values()

        # check archive synch with remote, fix if needed
        if action not in [u"collection-status",
                          u"remove-all-but-n-full",
                          u"remove-all-inc-of-but-n-full",
                          u"remove-old",
                          u"replicate",
                              ]:

            sync_archive(col_stats)

        while True:
            # if we have to clean up the last partial, then col_stats are invalidated
            # and we have to start the process all over again until clean.
            if action in [u"full", u"inc", u"cleanup"]:
                last_full_chain = col_stats.get_last_backup_chain()
                if not last_full_chain:
                    break
                last_backup = last_full_chain.get_last()
                if last_backup.partial:
                    if action in [u"full", u"inc"]:
                        # set restart parms from last_backup info
                        config.restart = Restart(last_backup)
                        # (possibly) reset action
                        action = config.restart.type
                        # reset the time strings
                        if action == u"full":
                            dup_time.setcurtime(config.restart.time)
                        else:
                            dup_time.setcurtime(config.restart.end_time)
                            dup_time.setprevtime(config.restart.start_time)
                        # log it -- main restart heavy lifting is done in write_multivol
                        log.Notice(_(u"Last %s backup left a partial set, restarting." % action))
                        break
                    else:
                        # remove last partial backup and get new collection status
                        log.Notice(_(u"Cleaning up previous partial %s backup set, restarting." % action))
                        last_backup.delete()
                        col_stats = dup_collections.CollectionsStatus(config.backend,
                                                                    config.archive_dir_path,
                                                                    action).set_values()
                        continue
                break
            break

        # OK, now we have a stable collection
        last_full_time = col_stats.get_last_full_backup_time()
        if last_full_time > 0:
            log.Notice(_(u"Last full backup date:") + u" " + dup_time.timetopretty(last_full_time))
        else:
            log.Notice(_(u"Last full backup date: none"))
        if not config.restart and action == u"inc" and config.full_force_time is not None and \
        last_full_time < config.full_force_time:
            log.Notice(_(u"Last full backup is too old, forcing full backup"))
            action = u"full"

        # get the passphrase if we need to based on action/options
        config.gpg_profile.passphrase = get_passphrase(1, action)

        if action == u"restore":
            restore(col_stats)
        elif action == u"verify":
            self.verify(col_stats)
        elif action == u"list-current":
            self.list_current(col_stats)
        elif action == u"collection-status":
            if config.show_changes_in_set is not None:
                log.PrintCollectionChangesInSet(col_stats, config.show_changes_in_set, True)
            elif not config.file_changed:
                log.PrintCollectionStatus(col_stats, True)
            else:
                log.PrintCollectionFileChangedStatus(col_stats, config.file_changed, True)
            self.chain_dict = self.get_chain_dict(col_stats)
        elif action == u"cleanup":
            cleanup(col_stats)
        elif action == u"remove-old":
            remove_old(col_stats)
        elif action == u"remove-all-but-n-full" or action == u"remove-all-inc-of-but-n-full":
            remove_all_but_n_full(col_stats)
        elif action == u"sync":
            sync_archive(col_stats)
        elif action == u"replicate":
            replicate()
        else:
            assert action == u"inc" or action == u"full", action
            # the passphrase for full and inc is used by --sign-key
            # the sign key can have a different passphrase than the encrypt
            # key, therefore request a passphrase
            if config.gpg_profile.sign_key:
                config.gpg_profile.signing_passphrase = get_passphrase(1, action, True)

            # if there are no recipients (no --encrypt-key), it must be a
            # symmetric key. Therefore, confirm the passphrase
            if not (config.gpg_profile.recipients or config.gpg_profile.hidden_recipients):
                config.gpg_profile.passphrase = get_passphrase(2, action)
                # a limitation in the GPG implementation does not allow for
                # inputting different passphrases, this affects symmetric+sign.
                # Allow an empty passphrase for the key though to allow a non-empty
                # symmetric key
                if (config.gpg_profile.signing_passphrase and
                        config.gpg_profile.passphrase != config.gpg_profile.signing_passphrase):
                    log.FatalError(_(
                        u"When using symmetric encryption, the signing passphrase "
                        u"must equal the encryption passphrase."),
                        log.ErrorCode.user_error)

            if action == u"full":
                full_backup(col_stats)
            else:  # attempt incremental
                sig_chain = check_sig_chain(col_stats)
                # action == "inc" was requested, but no full backup is available
                if not sig_chain:
                    full_backup(col_stats)
                else:
                    if not config.restart:
                        # only ask for a passphrase if there was a previous backup
                        if col_stats.all_backup_chains:
                            config.gpg_profile.passphrase = get_passphrase(1, action)
                            check_last_manifest(col_stats)  # not needed for full backups
                    incremental_backup(sig_chain)
        config.backend.close()
        if exit_val is not None:
            print(exit_val)

    def get_chain_dict(self, col_stats):
        """Adapted from https://gitlab.com/duplicity/duplicity

        :param col_stats: Collection status of Target
        :type col_stats: dup_collections.CollectionsStatus
        :return: Snapshots
        :rtype:dict
        """
        d = {}
        if col_stats.matched_chain_pair:
            for s in col_stats.matched_chain_pair[1].get_all_sets():
                if s.time:
                    btype = _(u"Full")
                    time = s.time
                else:
                    btype = _(u"Incremental")
                    time = s.end_time

                d[time] = (btype, dup_time.timetopretty(time), len(s))

        for i in range(len(col_stats.other_backup_chains)):
            for s in col_stats.other_backup_chains[i].get_all_sets():
                if s.time:
                    btype = _(u"Full")
                    time = s.time
                else:
                    btype = _(u"Incremental")
                    time = s.end_time

                d[time] = (btype, dup_time.timetopretty(time), len(s))

        return d

    def list_current(self, col_stats, time=None):
        """Adapted from https://gitlab.com/duplicity/duplicity/
        List the files current in the archive (examining signature only)

        :type col_stats: CollectionStatus object
        :param col_stats: collection status

        :rtype: void
        :return: void
        """
        if not time:
            time = config.restore_time or dup_time.curtime
        sig_chain = col_stats.get_signature_chain_at_time(time)
        self.current_paths = diffdir.get_combined_path_iter(
                                sig_chain.get_fileobjs(time)
                                )

    def verify(self, col_stats):
        """Adapted from https://gitlab.com/duplicity/duplicity/
        Verify files, logging differences

        @type col_stats: CollectionStatus object
        @param col_stats: collection status

        @rtype: void
        @return: void
        """
        global exit_val
        collated = diffdir.collate2iters(restore_get_patched_rop_iter(col_stats),
                                        config.select)
        diff_count = 0
        total_count = 0
        self.diff_f_list = {}
        for backup_ropath, current_path in collated:
            
            if not backup_ropath:
                backup_ropath = path.ROPath(current_path.index)
            if not current_path:
                current_path = path.ROPath(backup_ropath.index)
            if not backup_ropath == current_path:
                diff_count += 1
                self.diff_f_list[util.uindex(backup_ropath.index)] = backup_ropath.type
            total_count += 1
        # Unfortunately, ngettext doesn't handle multiple number variables, so we
        # split up the string.
        #log.Notice(_(u"Verify complete: %s, %s.") %
        #        (_(u"%d file(s) compared") % total_count,
        #            _(u"%d difference(s) found") % diff_count))
        if diff_count >= 1:
            exit_val = 1
