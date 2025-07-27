# find_ssh_gpg_keys/config.py

# --- Core search targets ---
# Directories that the script will look for
TARGET_DIRS = {".ssh", "gnupg", ".gnupg"}

# --- Scan exclusion lists ---
# System and service directories to skip during the scan
SYSTEM_DIRS_TO_SKIP = {
    "$recycle.bin", "system volume information", "config.msi",
    "documents and settings", "application data", "recovery",
    "windows", "programdata", "perflogs", "node_modules",
    ".git", "AppData", "Program Files", "Program Files(x86)",
    "Temp",
}

# User-specific directories that should also be skipped
USER_DIRS_TO_SKIP = {"Photos", "Videos", "Music", "Downloads", "Documents"}


# --- File patterns for filtering during copy ---
# Files to exclude from the final archive (e.g., help files)
EXCLUDE_FILE_PATTERNS = ["help.txt", "help.*.txt", "*.hlp"]

# Key files to copy when using the --only-key-files flag
# 'known_hosts' is added as an important SSH file
INCLUDE_KEY_PATTERNS = ["*.key", "*.pub", "id_rsa", "id_ed25519", "known_hosts"]