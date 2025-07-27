# find_ssh_gpg_keys/core.py

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
    Функция, работающая в отдельном потоке для отображения прогресса.
    Обновляет одну строку в консоли сводной информацией.
    """
    spinner_chars = ['|', '/', '-', '\\']
    spinner_index = 0

    while not stop_event.is_set():
        # Получаем текущий символ для спиннера
        spinner_char = spinner_chars[spinner_index]
        spinner_index = (spinner_index + 1) % len(spinner_chars)

        summary = stats.get_summary()
        warn_items = summary['warnings'].items()
        warn_str = ", ".join(
            [f"{k}: {v}" for k, v in warn_items]) if warn_items else "None"

        # Добавляем спиннер в начало строки состояния
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


# --- Остальной код в файле core.py остается без изменений ---

def should_skip_dir(dir_path: Path, exclude_dirs: Optional[Set[str]] = None) -> bool:
    """Проверяет, следует ли пропустить директорию."""
    path_parts = {part.lower() for part in dir_path.parts}
    if any(skip_dir.lower() in path_parts for skip_dir in SYSTEM_DIRS_TO_SKIP):
        return True
    if dir_path.name.lower() in {name.lower() for name in USER_DIRS_TO_SKIP}:
        return True
    if exclude_dirs and dir_path.name.lower() in exclude_dirs:
        return True
    return False


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
    Рекурсивно сканирует директории, обновляя объект статистики.
    """
    stats.increment_scanned()

    if current_abs_depth > max_depth:
        return

    try:
        entries = [entry for entry in start_path.iterdir() if entry.is_dir()]
        entries = filter_dirs(entries, exclude_dirs)

        sub_tasks = []
        for entry in entries:
            if should_skip_dir(entry, exclude_dirs):
                continue
            if entry.name.lower() in target_dirs:
                stats.add_found_key(entry)
            else:
                sub_tasks.append(entry)

        if current_abs_depth < max_depth:
            if parallel:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(
                            scan_for_target_dirs,
                            task, max_depth, target_dirs, exclude_dirs, stats,
                            current_abs_depth + 1, parallel, max_workers
                        ) for task in sub_tasks
                    }
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            stats.add_warning("Scan Error")
                            logging.error(f"Error in parallel task: {e}")
            else:
                for task in sub_tasks:
                    scan_for_target_dirs(
                        task, max_depth, target_dirs, exclude_dirs, stats,
                        current_abs_depth + 1, parallel, max_workers
                    )
    except (PermissionError, OSError):
        stats.add_warning("Access Denied")
    except Exception:
        stats.add_warning("Read Error")


def copy_and_archive(
        found_dirs: List[Path],
        output_base_dir: Path,
        show_progress: bool = False,
        no_archive: bool = False,
        only_key_files: bool = False,
        dry_run: bool = False,
) -> Tuple[Path, Optional[Path]]:
    """Копирует найденные директории и создаёт архив."""
    output_dir_path = output_base_dir / f"found_keys_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if not dry_run:
        output_dir_path.mkdir(parents=True, exist_ok=True)

    def ignore_logic(_, names):
        ignored_names = set()
        if only_key_files:
            for name in names:
                is_key_file = any(
                    fnmatch.fnmatch(name, pat) for pat in INCLUDE_KEY_PATTERNS)
                if not is_key_file:
                    ignored_names.add(name)
        else:
            for name in names:
                if any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_FILE_PATTERNS):
                    ignored_names.add(name)
        return list(ignored_names)

    iterator = tqdm(found_dirs, desc="Copying keys",
                    unit="dir") if show_progress else found_dirs
    copied_count, skipped_count = 0, 0

    for idx, folder in enumerate(iterator):
        dest_name = f"{folder.parent.name.replace(':', '')}_{folder.name}_{idx}"
        dest = output_dir_path / dest_name

        if dry_run:
            logging.info(f"DRY RUN: Would copy '{folder}' to '{dest}'")
            continue

        try:
            shutil.copytree(folder, dest, ignore=ignore_logic, dirs_exist_ok=True)
            logging.info(f"Copied '{folder}' to '{dest}'")
            copied_count += 1
        except (OSError, IOError) as e:
            logging.error(f"Failed to copy '{folder}': {e}")
            skipped_count += 1

    archive_file = None
    if not no_archive and not dry_run and copied_count > 0:
        if show_progress:
            print(f"Creating archive...")
        archive_base_name = output_dir_path
        try:
            archive_file_str = shutil.make_archive(str(archive_base_name), "zip",
                                                   root_dir=output_dir_path)
            archive_file = Path(archive_file_str)
            logging.info(f"Archive created: {archive_file}")
        except Exception as e:
            logging.error(f"Failed to create archive: {e}")

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
    """Основная функция для поиска и архивации ключей."""
    stats = ScanStats()
    stop_event = threading.Event()
    display_thread = None

    if show_progress:
        display_thread = threading.Thread(target=display_progress,
                                          args=(stats, stop_event))
        display_thread.daemon = True
        display_thread.start()

    scan_paths = drives
    target_dirs_set = set(t.lower() for t in target_dirs)

    # Создаем пул потоков для каждого диска
    # Ограничим количество одновременных потоков для дисков, чтобы не перегружать систему
    drive_workers = min(len(scan_paths), 4)
    with ThreadPoolExecutor(max_workers=drive_workers,
                            thread_name_prefix='drive_scanner') as executor:
        futures = []
        for drive_path_str in scan_paths:
            drive_path = Path(drive_path_str)
            if not drive_path.exists():
                logging.warning(f"Drive {drive_path} does not exist, skipping.")
                continue

            # Каждое сканирование диска - это отдельная задача
            future = executor.submit(
                scan_for_target_dirs,
                start_path=drive_path,
                max_depth=max_depth,
                target_dirs=target_dirs_set,
                exclude_dirs=exclude_dirs,
                stats=stats,
                parallel=parallel,  # Внутренняя параллелизация для папок
                max_workers=max_workers,
            )
            futures.append(future)

        # Ожидаем завершения сканирования всех дисков
        for future in as_completed(futures):
            try:
                future.result()  # Получаем результат, чтобы отловить возможные ошибки
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