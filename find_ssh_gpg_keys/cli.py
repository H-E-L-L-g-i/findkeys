# find_ssh_gpg_keys/cli.py

import click
import logging
import os
import sys
from pathlib import Path

from .core import find_and_archive_keys
from .utils import get_available_drives, setup_logging, parse_comma_list, is_windows
from .config import TARGET_DIRS


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option('1.3.0')
def cli(ctx):
    """
    A utility to find and archive GPG/SSH keys.

    Run without a command to see this help message.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)


@cli.command()
@click.option('--drives',
              help='Comma-separated drives to scan (e.g., c,d). Default: all available.')
@click.option('--max-depth', default=5, type=int,
              help='Maximum scan depth per directory.')
@click.option('--target-dirs', default=','.join(TARGET_DIRS),
              help='Target directories to search for.')
@click.option('--output-dir', type=click.Path(file_okay=False, path_type=Path),
              default=Path.home() / "Desktop",
              help='Directory to save the results.')
@click.option('--parallel/--no-parallel', default=True,
              help='Enable/disable parallel scanning.')
@click.option('--max-workers', default=None, type=int,
              help='Max threads for scanning (default: auto).')
@click.option('--show-progress/--no-show-progress', default=True,
              help='Show a dynamic status line.')
@click.option('--exclude-dirs', default='', help='Comma-separated directories to exclude from search.')
@click.option('--no-archive', is_flag=True, help='Disable creating a ZIP archive.')
@click.option('--only-key-files', is_flag=True, help='Copy only key files (e.g., *.key, id_rsa).')
@click.option('--log-file', type=click.Path(dir_okay=False, path_type=Path),
              help='Path to the log file.')
@click.option('--dry-run', is_flag=True, help='Simulate a run without copying or archiving files.')
@click.option('--list-drives', is_flag=True, help='List available drives and exit.')
@click.option('--verbose', is_flag=True,
              help='Show detailed log messages in the console.')
def scan(
        drives, max_depth, target_dirs, output_dir, parallel, max_workers,
        show_progress, exclude_dirs, no_archive, only_key_files, log_file, dry_run,
        list_drives, verbose
):
    """Scan drives, copy keys, and create an archive."""
    setup_logging(str(log_file) if log_file else None, verbose=verbose)

    available_drives = get_available_drives()

    if list_drives:
        print("Available drives:", ", ".join(available_drives))
        sys.exit(0)

    scan_paths = []
    if drives:
        selected_drives = parse_comma_list(drives)
        if is_windows():
            # Normalize drive letters to "C:\\" format
            scan_paths = [f"{d.upper()}:\\" if len(d) == 1 else d for d in
                          selected_drives]
        else:
            scan_paths = selected_drives
    else:
        logging.info("No drives specified, scanning all available ones.")
        scan_paths = available_drives

    if max_workers is None:
        # Set a reasonable default for worker threads
        max_workers = min(32, (os.cpu_count() or 1) + 4)

    try:
        output_path, archive_path = find_and_archive_keys(
            drives=scan_paths,
            max_depth=max_depth,
            target_dirs=parse_comma_list(target_dirs),
            output_dir=output_dir,
            parallel=parallel,
            max_workers=max_workers,
            show_progress=show_progress,
            exclude_dirs=set(d.lower() for d in parse_comma_list(exclude_dirs)),
            no_archive=no_archive,
            only_key_files=only_key_files,
            dry_run=dry_run,
        )

        click.secho("\n[SUCCESS] Scan completed!", fg='green')
        click.echo(f"[INFO] Results saved to: {output_path}")
        if archive_path:
            click.echo(f"[INFO] Archive created: {archive_path}")
        elif not dry_run:
            click.secho("[INFO] Archive was not created.", fg='yellow')

    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
        click.secho(f"[ERROR] An unexpected error occurred: {e}", fg='red')
        sys.exit(1)


def main():
    cli()


if __name__ == '__main__':
    main()