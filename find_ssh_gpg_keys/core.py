import logging
import shutil
import sys
import time
import threading
import fnmatch
from pathlib import Path
from typing import List, Optional, Set, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm

from .stats import ScanStats
from .utils import filter_dirs
from .config import (
    TARGET_DIRS,
    SYSTEM_DIRS_TO_SKIP,
    USER_DIRS_TO_SKIP,
    EXCLUDE_FILE_PATTERNS,
    INCLUDE_KEY_PATTERNS,
)


def display_progress(stats: ScanStats, stop_event: threading.Event):
    """
    Displays progress in a separate thread.
    Updates a single line in the console with summary information.
    """
    spinner_chars = ['|', '/', '-', '\\']
    spinner_index = 0

    while not stop_event.is_set():
        spinner_char = spinner_chars[spinner_index]
        spinner_index = (spinner_index + 1) % len(spinner_chars)

        summary = stats.get_summary()
        warn_items = summary['warnings'].items()
        warn_str = ", ".join(
            [f"{k}: {v}" for k, v in warn_items]) if warn_items else "None"

        status_line = (
            f"[{spinner_char}] "
            f"Dirs scanned: {summary['scanned']:,} | "
            f"Keys found: {summary['found']} | "
            f"Warnings: [{warn_str}]"
        )

        sys.stdout.write(f"\r{status_line.ljust(100)}")
        sys.stdout.flush()
        time.sleep(0.2)

    sys.stdout.write("\r" + " " * 100 + "\r")
    sys.stdout.flush()


def should_skip_dir(dir_path: Path, exclude_dirs: Optional[Set[str]] = None) -> bool:
    """Checks if a directory should be skipped."""
    path_parts = {part.lower() for part in dir_path.parts}
    if any(skip_dir.lower() in path_parts for skip_dir in SYSTEM_DIRS_TO_SKIP):
        return True
    if dir_path.name.lower() in {name.lower() for name in USER_DIRS_TO_SKIP}:
        return True
    if exclude_dirs and dir_path.name.lower() in exclude_dirs:
        return True
    return False


def is_valid_key_dir(dir_path: Path) -> bool:
    """
    Checks if a directory contains at least one file or subdirectory
    that matches the patterns for key files. This helps to filter out
    directories that have the right name (e.g., 'gnupg') but don't
    contain actual keys (e.g., only socket files).
    """
    try:
        for entry in dir_path.iterdir():
            # For directories, match patterns ending with '/'
            if entry.is_dir():
                if any(fnmatch.fnmatch(entry.name + "/", pat) for pat in INCLUDE_KEY_PATTERNS):
                    return True
            # For files, match file patterns
            else:
                if any(fnmatch.fnmatch(entry.name, pat) for pat in INCLUDE_KEY_PATTERNS):
                    return True
    except OSError as e:
        logging.warning(f"Could not validate directory content of {dir_path}: {e}")
        return False  # If we can't read it, we can't validate it.

    return False


def _process_directory(
        entry: Path,
        target_dirs: Set[str],
        exclude_dirs: Set[str],
        stats: ScanStats
) -> bool:
    """
    Processes a single directory entry. Adds to stats if it's a valid key dir.
    Returns True if the directory should be queued for deeper scanning.
    """
    if should_skip_dir(entry, exclude_dirs):
        return False

    if entry.name.lower() in target_dirs:
        if is_valid_key_dir(entry):
            stats.add_found_key(entry)
        else:
            logging.info(f"Skipping '{entry}' as it doesn't contain recognizable key files.")
        return False  # It's a target, don't scan deeper

    return True  # Not a target, queue for deeper scan


def _scan_sequentially(
        tasks: List[Path], max_depth: int, target_dirs: Set[str],
        exclude_dirs: Set[str], stats: ScanStats, current_abs_depth: int,
        parallel: bool, max_workers: int
):
    """Handles recursive scanning sequentially."""
    for task in tasks:
        scan_for_target_dirs(
            task, max_depth, target_dirs, exclude_dirs, stats,
            current_abs_depth, parallel, max_workers
        )


def _scan_in_parallel(
        tasks: List[Path], max_depth: int, target_dirs: Set[str],
        exclude_dirs: Set[str], stats: ScanStats, current_abs_depth: int,
        parallel: bool, max_workers: int
):
    """Handles recursive scanning in parallel."""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                scan_for_target_dirs,
                task, max_depth, target_dirs, exclude_dirs, stats,
                current_abs_depth, parallel, max_workers
            ) for task in tasks
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                stats.add_warning("Scan Error")
                logging.error(f"Error in parallel task: {e}")


def scan_for_target_dirs(
        start_path: Path,
        max_depth: int,
        target_dirs: Set[str],
        exclude_dirs: Set[str],
        stats: ScanStats,
        current_abs_depth: int = 0,
        parallel: bool = False,
        max_workers: int = 8,
):
    """
    Recursively scans directories, updating the statistics object.
    """
    stats.increment_scanned()
    if current_abs_depth >= max_depth:
        return

    try:
        entries = [entry for entry in start_path.iterdir() if entry.is_dir()]
        processable_entries = filter_dirs(entries, exclude_dirs)

        sub_tasks = []
        for entry in processable_entries:
            if _process_directory(entry, target_dirs, exclude_dirs, stats):
                sub_tasks.append(entry)

        if not sub_tasks:
            return

        scan_args = (
            sub_tasks, max_depth, target_dirs, exclude_dirs, stats,
            current_abs_depth + 1, parallel, max_workers
        )
        if parallel:
            _scan_in_parallel(*scan_args)
        else:
            _scan_sequentially(*scan_args)
    except OSError:
        stats.add_warning("Access Denied")
    except Exception:
        stats.add_warning("Read Error")


def _get_ignore_func(only_key_files: bool):
    """
    Factory to create the ignore function for shutil.copytree based on copy mode.
    """

    def ignore_by_inclusion(root, names):
        """Ignore files and dirs NOT matching INCLUDE_KEY_PATTERNS."""
        ignored = set()
        for name in names:
            path_obj = Path(root) / name
            # Add trailing slash for directories to match patterns like "private-keys-v*/"
            match_name = name + "/" if path_obj.is_dir() else name
            is_included = any(fnmatch.fnmatch(match_name, pat) for pat in INCLUDE_KEY_PATTERNS)
            if not is_included:
                ignored.add(name)
        return list(ignored)

    def ignore_by_exclusion(_, names):
        """Ignore files matching EXCLUDE_FILE_PATTERNS."""
        ignored_names = []
        for name in names:
            if any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_FILE_PATTERNS):
                ignored_names.append(name)
        return ignored_names

    return ignore_by_inclusion if only_key_files else ignore_by_exclusion


def _copy_found_dirs(
        found_dirs: List[Path],
        output_dir_path: Path,
        ignore_func,
        show_progress: bool,
        dry_run: bool,
) -> Tuple[int, int]:
    """Copies directories from found_dirs to output_dir_path, returning counts."""
    copied_count, skipped_count = 0, 0
    iterator = tqdm(found_dirs, desc="Copying keys", unit="dir") if show_progress else found_dirs

    for idx, folder in enumerate(iterator):
        dest_name = f"{folder.parent.name.replace(':', '')}_{folder.name}_{idx}"
        dest = output_dir_path / dest_name

        if dry_run:
            logging.info(f"DRY RUN: Would copy '{folder}' to '{dest}'")
            continue

        try:
            shutil.copytree(folder, dest, ignore=ignore_func, dirs_exist_ok=True)
            logging.info(f"Copied '{folder}' to '{dest}'")
            copied_count += 1
        except OSError as e:
            logging.error(f"Failed to copy '{folder}': {e}")
            skipped_count += 1

    return copied_count, skipped_count


def _create_archive(
        output_dir_path: Path,
        show_progress: bool,
) -> Optional[Path]:
    """Creates a zip archive of the given directory."""
    if show_progress:
        print("Creating archive...")

    try:
        archive_file_str = shutil.make_archive(
            base_name=str(output_dir_path),
            format="zip",
            root_dir=output_dir_path
        )
        archive_file = Path(archive_file_str)
        logging.info(f"Archive created: {archive_file}")
        return archive_file
    except Exception as e:
        logging.error(f"Failed to create archive: {e}")
        return None


def copy_and_archive(
        found_dirs: List[Path],
        output_base_dir: Path,
        show_progress: bool = False,
        no_archive: bool = False,
        only_key_files: bool = False,
        dry_run: bool = False,
) -> Tuple[Path, Optional[Path]]:
    """Copies the found directories and creates an archive."""
    output_dir_path = output_base_dir / f"found_keys_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if not dry_run:
        output_dir_path.mkdir(parents=True, exist_ok=True)

    ignore_func = _get_ignore_func(only_key_files)

    copied_count, skipped_count = _copy_found_dirs(
        found_dirs, output_dir_path, ignore_func, show_progress, dry_run
    )

    archive_file = None
    if not no_archive and not dry_run and copied_count > 0:
        archive_file = _create_archive(output_dir_path, show_progress)

    logging.info(
        f"Scan complete. Found: {len(found_dirs)}, Copied: {copied_count}, Skipped: {skipped_count}.")
    return output_dir_path, archive_file


def find_and_archive_keys(
        drives: List[str],
        max_depth: int,
        target_dirs: List[str],
        output_dir: Path,
        exclude_dirs: Set[str],
        parallel: bool,
        max_workers: int,
        show_progress: bool,
        no_archive: bool,
        only_key_files: bool,
        dry_run: bool,
) -> Tuple[Path, Optional[Path]]:
    """The main function for finding and archiving keys."""
    stats = ScanStats()
    stop_event = threading.Event()
    display_thread = None

    if show_progress:
        display_thread = threading.Thread(target=display_progress,
                                          args=(stats, stop_event))
        display_thread.daemon = True
        display_thread.start()

    scan_paths = drives
    target_dirs_set = {t.lower() for t in target_dirs}

    # Limit the number of concurrent threads for drives to avoid overloading the system
    drive_workers = min(len(scan_paths), 4)
    with ThreadPoolExecutor(max_workers=drive_workers,
                            thread_name_prefix='drive_scanner') as executor:
        futures = []
        for drive_path_str in scan_paths:
            drive_path = Path(drive_path_str)
            if not drive_path.exists():
                logging.warning(f"Drive {drive_path} does not exist, skipping.")
                continue

            future = executor.submit(
                scan_for_target_dirs,
                start_path=drive_path,
                max_depth=max_depth,
                target_dirs=target_dirs_set,
                exclude_dirs=exclude_dirs,
                stats=stats,
                parallel=parallel,
                max_workers=max_workers,
            )
            futures.append(future)

        # Wait for all drive scans to complete
        for future in as_completed(futures):
            try:
                future.result()  # Get the result to catch potential errors
            except Exception as e:
                stats.add_warning("Drive Scan Error")
                logging.error(f"A critical error occurred during drive scan: {e}",
                              exc_info=True)

    if display_thread:
        stop_event.set()
        display_thread.join()

    found_dirs = stats.keys_found
    if not found_dirs:
        logging.info("No target directories found.")
        return output_dir, None

    logging.info(f"Found {len(found_dirs)} unique target directories.")

    return copy_and_archive(
        found_dirs=found_dirs,
        output_base_dir=output_dir,
        show_progress=show_progress,
        no_archive=no_archive,
        only_key_files=only_key_files,
        dry_run=dry_run,
    )