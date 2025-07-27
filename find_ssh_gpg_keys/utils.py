# find_ssh_gpg_keys/utils.py

from pathlib import Path
import shutil
import fnmatch
from typing import List, Set
import logging
import sys
import platform

BASE_DIR = Path(__file__).resolve().parent.parent


def setup_logging(log_file: str = None, verbose: bool = False) -> None:
    """
    Configures logging.
    - In quiet mode, only ERROR level and higher is sent to the console.
    - In verbose mode, INFO level and higher is sent to the console.
    - The log file always records INFO level and higher.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter = logging.Formatter("[%(levelname)s] %(asctime)s %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_level = logging.INFO if verbose else logging.ERROR
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def is_windows() -> bool:
    """Returns True if the operating system is Windows."""
    return platform.system() == "Windows"


def get_available_drives() -> List[str]:
    """Returns a list of available drives in the system."""
    if is_windows():
        drives = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive_path = Path(f"{letter}:\\")
            if drive_path.exists():
                drives.append(str(drive_path))
        return drives
    else:
        return ["/"]


def get_platform_root() -> Path:
    """Returns the root path depending on the platform."""
    return Path('C:/') if is_windows() else Path('/')


def parse_comma_list(value: str) -> List[str]:
    """Parses a comma-separated string into a list of strings."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def filter_dirs(entries: List[Path], exclude_dirs: Set[str]) -> List[Path]:
    """Filters a list of directories, excluding those in exclude_dirs."""
    return [entry for entry in entries if entry.name.lower() not in exclude_dirs]


def check_free_space(path: Path, required_bytes: int) -> bool:
    """Checks for sufficient free disk space."""
    usage = shutil.disk_usage(str(path))
    return usage.free >= required_bytes