"""
    Read and Write YAML configuration files
"""
import yaml


def read_config(path):
    """Read a config file

    Args:
        path (str): Path of the config file

    Returns:
        dict: Config YAML file as dictionary
    """
    with open(path, "r", encoding='UTF-8') as f_file:
        data = yaml.safe_load(f_file)
    return data


def write_config(cfg, path):
    """Write a dictionary to YAML config file

    Args:
        cfg (dict): config as dictionary
        path (str): Save path of config file
    """
    with open(path, 'w', encoding='UTF-8') as f_file:
        yaml.dump(cfg, f_file, default_flow_style=False)
