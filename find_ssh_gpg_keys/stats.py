# find_ssh_gpg_keys/stats.py

import threading
from collections import Counter
from pathlib import Path
from typing import List, Dict

class ScanStats:
    """
    A thread-safe class for collecting scan statistics.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.dirs_scanned: int = 0
        self.warnings: Counter = Counter()
        self.keys_found: List[Path] = []

    def increment_scanned(self):
        """Increments the counter for scanned directories."""
        with self._lock:
            self.dirs_scanned += 1

    def add_warning(self, warn_type: str):
        """Adds a warning, grouping by type."""
        with self._lock:
            self.warnings[warn_type] += 1

    def add_found_key(self, path: Path):
        """Adds a path to the list of found keys."""
        with self._lock:
            if path not in self.keys_found:
                self.keys_found.append(path)

    def get_summary(self) -> Dict:
        """Returns a summary of the current statistics."""
        with self._lock:
            # Return a copy to avoid long lock holds
            return {
                "scanned": self.dirs_scanned,
                "warnings": dict(self.warnings),
                "found": len(self.keys_found),
            }