# Kyrian
A frontend for the backup software [duplicity](https://gitlab.com/duplicity/duplicity). 

⚠️ **Kyrian is still in development and lacks some functinality**

# Installation

```
pip install .
```

# Usage

Execute `kyrian`.
Source directory and target server (e.g. `file://my_local_folder, ftp://user@host/my_folder`) can be modified via the Settings Panel or by modifying `~/.config/kyrian/config.yaml`

```
Profile: Default
Profiles:
  Default:
    Source: my_source_dir
    Target: file://my_local_folder
    encrypt: true
    encrypt-key: 1234567890ABCDEF
    encrypt-sign-key: 1234567890ABCDEF
    use-agent: true
```
The interface is self-explenatory and allows creating and restoring backups, lists available snapshots on the `Target` and displays contents of snapshots in the tree-view. It also allows restoring single files or directories via context menu.
