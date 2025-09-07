# --- Core search targets ---
# Directories that the script will look for
TARGET_DIRS = {".ssh", "gnupg", ".gnupg"}

# --- Scan exclusion lists ---
# System and service directories to skip during the scan
SYSTEM_DIRS_TO_SKIP = {
    "$recycle.bin", "system volume information", "config.msi",
    "recovery",
    "windows", "programdata", "perflogs", "node_modules",
    ".git", "Program Files", "Program Files (x86)", "Temp",
    "lib", "doc", "bin", "share",
}

# User-specific directories that should also be skipped
USER_DIRS_TO_SKIP = {"Photos", "Videos", "Music"}
# or you can exclude "Downloads", "Documents" by uncommenting the line below
# USER_DIRS_TO_SKIP = {"Photos", "Videos", "Music", "Downloads", "Documents"}


# --- File patterns for filtering during copy ---
# Files to exclude from the final archive (e.g., help files)
EXCLUDE_FILE_PATTERNS = [
    "*.exe", "*.dll", "*.so", "*.bin", "*.dat", "*.log", "*.tmp", "*.lock",
    "S.*",  # GPG socket files
    "*.old", "*_old", "*.bak", "*~",  # Common backup file patterns
    "known_hosts?*",  # Specific backup patterns for known_hosts
    "*.bat", "*.msi", "*.sh",
    "*.pdf", "*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp",
    "*.mo", "*.po",
    "help.txt", "help.*.txt", "*.hlp"
]

# Key files to copy when using the --only-key-files flag
# 'known_hosts' is added as an important SSH file

# --- Useful keys ---
INCLUDE_KEY_PATTERNS = [
    # GPG
    "private-keys-v*/",     # folder with private keys (v1, v2, ...)
    "openpgp-revocs.d/",    # revocation certificates folder
    "public-keys.d/",       # GPG public keys folder
    "*.gpg",                # individual GPG files
    "pubring.kbx",          # public keyring
    "trustdb.gpg",          # trust database
    "random_seed",          # entropy file
    "common.conf",          # config file

    # SSH
    "id_*",                 # SSH private keys
    "*.pub",                # SSH public keys
    "authorized_keys",      # list of authorized keys
    "config",               # SSH config file
    "known_hosts",          # saved hosts
]