"""Interactive menu-driven CLI for ProtonTune."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any, Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from protontune import __app_name__, __version__
from protontune.config import (
    create_backup,
    get_all_localconfig_paths,
    get_config_vdf_path,
    get_first_localconfig_vdf,
    list_backups,
    restore_backup,
    write_launch_options,
    write_proton_version,
)
from protontune.exceptions import (
    add_exclusion,
    get_forced_options,
    get_forced_proton,
    is_excluded,
    load_exceptions,
    remove_exclusion,
    save_exceptions,
    set_forced_options,
    set_forced_proton,
)
from protontune.hardware import detect_hardware, is_steam_running
from protontune.models import GPUVendor, SteamGame
from protontune.proton import scan_proton_versions
from protontune.protondb import (
    download_and_extract,
    find_dump_file,
    get_dump_info,
    list_available_dumps,
    load_reports_for_game,
)
from protontune.scoring import score_recommendations
from protontune.settings import get_setting, load_settings, save_settings, update_setting
from protontune.steam import scan_installed_games
from protontune.utils import ensure_config_dir

console = Console()
_err = Console(stderr=True)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _print_header(title: str) -> None:
    """Print a section header."""
    console.print()
    console.print(Panel(f"[bold cyan]{title}[/]", box=box.ROUNDED))
    console.print()


def _print_error(msg: str) -> None:
    """Print an error message."""
    _err.print(f"[bold red]Error:[/] {msg}")


def _print_success(msg: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]✓[/] {msg}")


def _print_warning(msg: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]⚠[/] {msg}")


def _print_info(msg: str) -> None:
    """Print an info message."""
    console.print(f"[bold blue]ℹ[/] {msg}")


def _wait_for_enter() -> None:
    """Prompt the user to press Enter to continue."""
    console.print()
    Prompt.ask("[dim]Press Enter to continue[/]", default="")
    console.print()


def _check_steam_closed() -> bool:
    """Check if Steam is running and warn the user."""
    if is_steam_running():
        _print_error(
            "Steam is currently running. All Steam configuration changes require "
            "Steam to be fully closed. Please exit Steam and try again."
        )
        return False
    return True


def _gpu_vendor_display(vendor: GPUVendor) -> str:
    """Return a display-friendly GPU vendor string."""
    return {
        GPUVendor.NVIDIA: "NVIDIA",
        GPUVendor.AMD: "AMD",
        GPUVendor.INTEL: "Intel",
        GPUVendor.UNKNOWN: "Unknown",
    }.get(vendor, "Unknown")


def _select_games(games: list[SteamGame]) -> list[SteamGame]:
    """Show an interactive game picker and return the user's selection.

    Lets the user select games by number (single, comma-separated, or range).
    Returns the list of selected SteamGame objects.
    """
    if not games:
        _print_warning("No games found. Run option 1 (Scan) first.")
        return []

    _print_header("Select Games")

    # Paginate if more than 30 games
    page_size = 30
    total_pages = max(1, (len(games) + page_size - 1) // page_size)
    current_page = 0
    selected: list[SteamGame] = []

    while True:
        start = current_page * page_size
        end = min(start + page_size, len(games))
        page_games = games[start:end]

        console.clear()
        _print_header(f"Select Games (page {current_page + 1}/{total_pages})")

        table = Table(box=box.SQUARE)
        table.add_column("#", style="bold cyan", width=4)
        table.add_column("AppID", style="dim", width=10)
        table.add_column("Name")

        for i, game in enumerate(page_games, start + 1):
            excluded = "[dim]  (excluded)[/]" if is_excluded(game.app_id) else ""
            table.add_row(str(i), game.app_id, f"{game.name}{excluded}")

        console.print(table)
        console.print()
        console.print("[dim]Select by number (e.g. 3), range (3-8), or comma-separated (1,4,7)[/]")
        console.print("[dim]Type [bold]n[/] for next page, [bold]p[/] for previous, [bold]a[/] for all, [bold]done[/] to finish[/]")
        console.print()

        choice = Prompt.ask("[bold]Your selection[/]", default="done").strip().lower()

        if choice == "done":
            break
        elif choice == "a":
            selected = [g for g in games if not is_excluded(g.app_id)]
            skipped = len(games) - len(selected)
            msg = f"Selected all {len(selected)} games"
            if skipped:
                msg += f" ({skipped} excluded skipped)"
            _print_success(msg)
            break
        elif choice == "n":
            if current_page < total_pages - 1:
                current_page += 1
            continue
        elif choice == "p":
            if current_page > 0:
                current_page -= 1
            continue
        else:
            # Parse selection: single, range, or comma-separated
            indices: list[int] = []
            for part in choice.split(","):
                part = part.strip()
                if "-" in part:
                    try:
                        lo, hi = part.split("-", 1)
                        indices.extend(range(int(lo) - 1, int(hi)))
                    except ValueError:
                        continue
                else:
                    try:
                        indices.append(int(part) - 1)
                    except ValueError:
                        continue

            for idx in indices:
                if 0 <= idx < len(games):
                    game = games[idx]
                    if not is_excluded(game.app_id) and game not in selected:
                        selected.append(game)

            _print_success(f"{len(selected)} game(s) selected so far")
            _wait_for_enter()

    console.clear()
    if selected:
        _print_success(f"{len(selected)} game(s) selected")
    else:
        _print_info("No games selected.")
    return selected


# ─── Menu ───────────────────────────────────────────────────────────────────

def _show_home_menu() -> int:
    """Display the home menu and return the user's choice."""
    console.clear()
    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]{__app_name__}[/] [white]v{__version__}[/]\n"
            "[dim]Steam Proton Optimizer[/]",
            box=box.DOUBLE_EDGE,
        )
    )
    console.print()

    menu_items = [
        ("1", "Scan library & hardware"),
        ("2", "View recommendations (dry-run, no changes)"),
        ("3", "Apply optimizations (creates a backup automatically)"),
        ("4", "Restore a previous backup"),
        ("5", "Refresh local ProtonDB data"),
        ("6", "Manage per-game exceptions"),
        ("7", "Settings"),
        ("0", "Exit"),
    ]

    table = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
    table.add_column("Key", style="bold cyan", width=3)
    table.add_column("Description")
    for key, desc in menu_items:
        table.add_row(key, desc)

    console.print(table)
    console.print()

    choice = Prompt.ask(
        "[bold]Select an option[/]",
        choices=[str(i) for i in range(8)],
        default="0",
    )
    return int(choice)


# ─── Menu Handlers ──────────────────────────────────────────────────────────

def _scan_library_and_hardware() -> None:
    """Menu option 1: scan and display results."""
    _print_header("System Scan")

    with console.status("[bold green]Detecting hardware..."):
        hardware = detect_hardware()

    with console.status("[bold green]Scanning Steam libraries..."):
        games = scan_installed_games()

    with console.status("[bold green]Scanning Proton installations..."):
        protons = scan_proton_versions()

    # Display hardware
    console.print(f"[bold]GPU Vendor:[/] {_gpu_vendor_display(hardware.gpu_vendor)}")
    if hardware.gpu_model:
        console.print(f"[bold]GPU Model:[/] {hardware.gpu_model}")
    console.print()

    # Display games
    console.print(f"[bold]Installed Games:[/] {len(games)} found")
    if games:
        game_table = Table(box=box.SIMPLE)
        game_table.add_column("AppID", style="dim", width=10)
        game_table.add_column("Name")
        for game in games[:30]:  # Limit display to 30
            game_table.add_row(game.app_id, game.name)
        if len(games) > 30:
            game_table.add_row("...", f"... and {len(games) - 30} more")
        console.print(game_table)

    # Display Proton versions
    if protons:
        console.print(f"\n[bold]Proton Versions:[/] {len(protons)} found")
        proton_table = Table(box=box.SIMPLE)
        proton_table.add_column("Name")
        proton_table.add_column("Type", width=14)
        for pv in protons:
            ptype = "[cyan]Official[/]" if not pv.is_custom else "[yellow]Custom[/]"
            proton_table.add_row(pv.name, ptype)
        console.print(proton_table)
    else:
        _print_warning("No Proton versions detected!")

    # Data dump status
    dump_info = get_dump_info()
    console.print()
    if dump_info:
        _print_info(
            f"ProtonDB data dump found: {dump_info['path']} "
            f"({dump_info['size_mb']} MB, {dump_info['format']})"
        )
    else:
        _print_warning(
            "No ProtonDB data dump found. Place a protondb_data.csv or .json "
            "file in ~/.config/steam-proton-optimizer/data/ to enable recommendations."
        )

    _wait_for_enter()


def _view_recommendations() -> None:
    """Menu option 2: select games and show dry-run recommendations."""
    _print_header("Recommendations (Dry Run)")

    dump_info = get_dump_info()
    if not dump_info:
        _print_error("No ProtonDB data dump found. Use option 5 to refresh data first.")
        _wait_for_enter()
        return

    with console.status("[bold green]Scanning..."):
        hardware = detect_hardware()
        games = scan_installed_games()
        protons = scan_proton_versions()

    if not games:
        _print_warning("No installed games detected!")
        _wait_for_enter()
        return

    if not protons:
        _print_warning("No Proton versions detected!")
        _wait_for_enter()
        return

    # Let user pick games
    selected = _select_games(games)
    if not selected:
        return

    min_reports = get_setting("min_reports_for_recommendation", 3)
    confidence_threshold = get_setting("confidence_threshold", 0.3)

    console.clear()
    _print_header("Recommendations")
    console.print(f"Hardware: [bold]{_gpu_vendor_display(hardware.gpu_vendor)}[/]"
                  f"{f' ({hardware.gpu_model})' if hardware.gpu_model else ''}")
    console.print()

    with console.status("[bold green]Generating recommendations..."):
        results: list[tuple[SteamGame, Optional[Any]]] = []
        for game in selected:
            reports = load_reports_for_game(game.app_id)
            if len(reports) < min_reports:
                results.append((game, None))
                continue
            rec = score_recommendations(game, reports, hardware, protons)
            results.append((game, rec))

    recommended_count = 0
    skipped_count = 0
    low_confidence_count = 0

    for game, rec in results:
        if not rec:
            skipped_count += 1
            continue

        if rec.score_confidence < confidence_threshold:
            low_confidence_count += 1

        table = Table(box=box.SQUARE, title=f"[bold]{game.name}[/] ({game.app_id})", title_style="bold")
        table.add_column("Setting", style="cyan", width=20)
        table.add_column("Value", style="white")

        if rec.proton_version:
            version_display = rec.proton_version.name
            if rec.fallback_version:
                version_display += " [yellow](fallback)[/]"
            table.add_row("Proton", version_display)
        else:
            table.add_row("Proton", "[dim]No recommendation[/]")

        table.add_row("Launch Options", rec.combined_launch_string or "[dim](none)[/]")
        table.add_row("Confidence", f"{rec.score_confidence:.0%} ({rec.total_reports_scored} reports)")

        if rec.launch_options:
            opts_table = Table(box=box.SIMPLE, show_header=True)
            opts_table.add_column("Option", style="yellow")
            opts_table.add_column("Score")
            opts_table.add_column("Reports")
            for opt in rec.launch_options[:5]:
                opts_table.add_row(
                    f"{opt.key}={opt.value}",
                    f"{opt.score:.3f}",
                    str(opt.source_report_count),
                )
            table.add_row("Top Options", opts_table)

        console.print(table)
        console.print()
        recommended_count += 1

    console.print(Panel(
        f"[bold]Summary[/]\n"
        f"Recommendations shown: {recommended_count}\n"
        f"Skipped (insufficient data): {skipped_count}\n"
        f"Low confidence: {low_confidence_count}",
        box=box.ROUNDED,
    ))

    _wait_for_enter()


def _apply_optimizations() -> None:
    """Menu option 3: select games and apply optimizations."""
    _print_header("Apply Optimizations")

    if not _check_steam_closed():
        _wait_for_enter()
        return

    dump_info = get_dump_info()
    if not dump_info:
        _print_error("No ProtonDB data dump found. Use option 5 to refresh data first.")
        _wait_for_enter()
        return

    config_vdf = get_config_vdf_path()
    localconfig_path = get_first_localconfig_vdf()

    if not config_vdf or not localconfig_path:
        _print_error("Could not locate Steam configuration files.")
        _wait_for_enter()
        return

    with console.status("[bold green]Scanning system..."):
        hardware = detect_hardware()
        games = scan_installed_games()
        protons = scan_proton_versions()

    if not games:
        _print_warning("No installed games detected!")
        _wait_for_enter()
        return

    if not protons:
        _print_warning("No Proton versions detected!")
        _wait_for_enter()
        return

    selected = _select_games(games)
    if not selected:
        return

    min_reports = get_setting("min_reports_for_recommendation", 3)
    confidence_threshold = get_setting("confidence_threshold", 0.3)

    to_apply: list[tuple[SteamGame, str, Optional[str], str]] = []

    with console.status("[bold green]Generating recommendations..."):
        for game in selected:
            if is_excluded(game.app_id):
                continue

            forced_opts = get_forced_options(game.app_id)
            forced_proton = get_forced_proton(game.app_id)

            if forced_opts is not None or forced_proton is not None:
                to_apply.append((
                    game,
                    forced_opts if forced_opts else "",
                    forced_proton,
                    "[yellow]forced (user exception)[/]",
                ))
                continue

            reports = load_reports_for_game(game.app_id)
            if len(reports) < min_reports:
                continue

            rec = score_recommendations(game, reports, hardware, protons)
            if not rec or rec.score_confidence < confidence_threshold:
                continue

            to_apply.append((
                game,
                rec.combined_launch_string,
                rec.proton_version.name if rec.proton_version else None,
                f"confidence {rec.score_confidence:.0%}",
            ))

    if not to_apply:
        _print_info("No optimizations available for the selected games.")
        _wait_for_enter()
        return

    console.clear()
    _print_header("Changes Preview")
    _print_warning(f"Steam must be closed. {len(to_apply)} game(s) will be modified.")
    console.print()

    change_table = Table(box=box.SQUARE)
    change_table.add_column("Game", style="bold")
    change_table.add_column("AppID", style="dim")
    change_table.add_column("Launch Options", style="cyan")
    change_table.add_column("Proton", style="yellow")
    change_table.add_column("Source")

    for game, opts, proton, reason in to_apply:
        change_table.add_row(
            game.name,
            game.app_id,
            opts or "[dim](clear)[/]",
            proton or "[dim](none)[/]",
            reason,
        )

    console.print(change_table)
    console.print()

    if not Confirm.ask("[bold yellow]Apply these changes?[/]", default=False):
        _print_info("Optimisation cancelled.")
        _wait_for_enter()
        return

    if not Confirm.ask(
        "[bold red]This will modify your Steam configuration. Are you sure?[/]",
        default=False,
    ):
        _print_info("Optimisation cancelled.")
        _wait_for_enter()
        return

    with console.status("[bold green]Creating backup..."):
        summary = f"{len(to_apply)} game(s) optimised"
        ts = create_backup(summary)

    if not ts:
        _print_error("Failed to create backup. Aborting.")
        _wait_for_enter()
        return

    _print_success(f"Backup created: {ts}")

    applied = 0
    errors = 0
    with console.status("[bold green]Applying..."):
        for game, opts, proton_name, _reason in to_apply:
            ok = True

            if not write_launch_options(game.app_id, opts, localconfig_path):
                _print_error(f"Failed: launch options for {game.name}")
                ok = False

            if proton_name and not write_proton_version(game.app_id, proton_name, config_vdf):
                _print_error(f"Failed: Proton version for {game.name}")
                ok = False

            if ok:
                applied += 1
            else:
                errors += 1

    console.print()
    _print_success(f"Applied: {applied} game(s)")
    if errors:
        _print_warning(f"Errors: {errors}")
        _print_info(f"A backup was saved as '{ts}' — you can restore via option 4.")
    _print_info("Start Steam for changes to take effect.")

    _wait_for_enter()


def _restore_backup() -> None:
    """Menu option 4: list and restore from a backup."""
    _print_header("Restore Backup")

    if not _check_steam_closed():
        _wait_for_enter()
        return

    backups = list_backups()
    if not backups:
        _print_info("No backups found.")
        _wait_for_enter()
        return

    table = Table(box=box.SQUARE)
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Timestamp", style="bold")
    table.add_column("Summary")
    table.add_column("Files")

    for i, b in enumerate(backups, 1):
        table.add_row(
            str(i),
            b["timestamp"],
            b.get("summary", "N/A"),
            str(b.get("files_backed_up", 0)),
        )

    console.print(table)
    console.print()

    choice = IntPrompt.ask(
        "[bold]Select a backup to restore (0 to cancel)[/]",
        default=0,
    )
    if choice <= 0 or choice > len(backups):
        _print_info("Restore cancelled.")
        _wait_for_enter()
        return

    selected = backups[choice - 1]["timestamp"]

    if not Confirm.ask(
        f"[bold red]Restore backup from {selected}? This will overwrite "
        f"your current Steam configuration.[/]",
        default=False,
    ):
        _print_info("Restore cancelled.")
        _wait_for_enter()
        return

    with console.status("[bold green]Restoring..."):
        ok = restore_backup(selected)

    if ok:
        _print_success(f"Backup {selected} restored successfully.")
        _print_info("Start Steam for the restored configuration to take effect.")
    else:
        _print_error(f"Failed to restore backup {selected}.")

    _wait_for_enter()


def _refresh_protondb_data() -> None:
    """Menu option 5: manage ProtonDB data — download from GitHub or refresh local data."""
    while True:
        _print_header("Refresh ProtonDB Data")

        dump_info = get_dump_info()
        if dump_info:
            _print_info(f"Current data: {dump_info['path']}")
            _print_info(f"Size: {dump_info['size_mb']} MB")
            _print_info(f"Last modified: {dump_info['modified']}")
            if "games" in dump_info:
                _print_info(f"Games indexed: {dump_info['games']}")
        else:
            _print_warning("No ProtonDB data dump found.")

        console.print()
        console.print("[bold]Options:[/]")
        console.print("  [cyan]1[/] Download latest data dump from GitHub (recommended)")
        console.print("  [cyan]2[/] List available dumps on GitHub")
        console.print("  [cyan]3[/] Show instructions for manual download")
        console.print("  [cyan]0[/] Back to main menu")
        console.print()

        choice = Prompt.ask(
            "[bold]Select an option[/]",
            choices=["0", "1", "2", "3"],
            default="0",
        )

        if choice == "0":
            break

        elif choice == "1":
            # Download latest
            _print_info("Fetching available dumps from GitHub...")
            dumps = list_available_dumps()
            if not dumps:
                _print_error(
                    "Could not fetch dump list from GitHub. "
                    "Check your internet connection and try again, "
                    "or use manual download (option 3)."
                )
                _wait_for_enter()
                continue

            latest = dumps[0]
            console.print()
            console.print(f"Latest available: [bold]{latest['name']}[/]")
            console.print(f"Size: {latest['size_mb']} MB")
            console.print(f"Source: {latest['url']}")
            console.print()

            if not Confirm.ask(
                "[bold yellow]Download and extract this dump?[/]",
                default=False,
            ):
                _print_info("Download cancelled.")
                _wait_for_enter()
                continue

            if not Confirm.ask(
                f"[bold red]This will download ~{latest['size_mb']} MB. Continue?[/]",
                default=False,
            ):
                _print_info("Download cancelled.")
                _wait_for_enter()
                continue

            with console.status(
                f"[bold green]Downloading and extracting {latest['name']}...[/]"
            ):
                ok = download_and_extract(latest["url"])

            if ok:
                _print_success(
                    f"Successfully downloaded and extracted {latest['name']}!"
                )
                new_info = get_dump_info()
                if new_info:
                    _print_info(f"Games indexed: {new_info.get('games', 'unknown')}")
            else:
                _print_error(
                    "Download or extraction failed. "
                    "Try manual download (option 3)."
                )

            _wait_for_enter()

        elif choice == "2":
            # List available dumps
            _print_info("Fetching available dumps from GitHub...")
            dumps = list_available_dumps()
            if not dumps:
                _print_error(
                    "Could not fetch dump list from GitHub. "
                    "Check your internet connection or use option 3 for manual setup."
                )
                _wait_for_enter()
                continue

            console.print(f"[bold]Available dumps on GitHub:[/] {len(dumps)}")
            console.print()

            table = Table(box=box.SQUARE)
            table.add_column("Snapshot", style="bold")
            table.add_column("Size", style="cyan")

            for dump in dumps[:20]:  # Show 20 most recent
                table.add_row(dump["name"], f"{dump['size_mb']} MB")

            if len(dumps) > 20:
                table.add_row("...", f"... and {len(dumps) - 20} more")

            console.print(table)
            _wait_for_enter()

        elif choice == "3":
            # Manual instructions
            console.print()
            console.print(
                "ProtonTune uses data from [bold]ProtonDB[/] (ODbL-licensed).\n"
                "The official data dumps are hosted on GitHub.\n\n"
                "[bold]Option A: Let ProtonTune download it automatically[/]\n"
                "  Select option 1 from this menu.\n\n"
                "[bold]Option B: Download manually[/]\n"
                "  1. Visit: [bold cyan]https://github.com/bdefore/protondb-data\n"
                "     blob/master/reports/[/]\n"
                "  2. Download the [bold]latest[/] reports_*.tar.gz file\n"
                "     (e.g., reports_jul1_2026.tar.gz, ~60 MB)\n"
                "  3. Extract it to:\n"
                "     [bold]~/.config/steam-proton-optimizer/data/[/]\n"
                "  4. The extracted [bold]reports/[/] directory should contain\n"
                "     one JSON file per game (e.g., 730.json for CS:GO/CS2).\n\n"
                "[bold]Note:[/] The data is provided under the Open Database License\n"
                "(ODbL). You're free to use it for any purpose, as long as you\n"
                "attribute ProtonDB and share-alike any derived databases."
            )
            console.print()

            # Check if manual file was placed
            if Confirm.ask("[bold]Check for data files now?[/]", default=True):
                new_info = get_dump_info()
                if new_info:
                    _print_success(f"Found: {new_info['path']}")
                    if "games" in new_info:
                        _print_info(f"Games indexed: {new_info['games']}")
                else:
                    _print_error(
                        "Still not found. Download and extract the tar.gz "
                        "to ~/.config/steam-proton-optimizer/data/"
                    )

            _wait_for_enter()


def _manage_exceptions() -> None:
    """Menu option 6: manage per-game exceptions."""
    while True:
        _print_header("Per-Game Exceptions")
        exceptions = load_exceptions()

        excludes = exceptions.get("exclude", [])
        forced_opts = exceptions.get("force_options", {})
        forced_proton = exceptions.get("force_proton", {})

        console.print(f"[bold]Excluded games:[/] {len(excludes)}")
        console.print(f"[bold]Forced launch options:[/] {len(forced_opts)}")
        console.print(f"[bold]Forced Proton versions:[/] {len(forced_proton)}")
        console.print()

        # Show current exceptions
        if excludes:
            console.print("[bold]Excluded AppIDs:[/]")
            for eid in excludes:
                console.print(f"  {eid}")
            console.print()

        if forced_opts:
            console.print("[bold]Forced Launch Options:[/]")
            for aid, opts in forced_opts.items():
                console.print(f"  [cyan]{aid}[/]: {opts}")
            console.print()

        if forced_proton:
            console.print("[bold]Forced Proton Versions:[/]")
            for aid, pname in forced_proton.items():
                console.print(f"  [cyan]{aid}[/]: {pname}")
            console.print()

        # Submenu
        console.print("[bold]Options:[/]")
        console.print("  [cyan]1[/] Add exclusion")
        console.print("  [cyan]2[/] Remove exclusion")
        console.print("  [cyan]3[/] Force launch options for an AppID")
        console.print("  [cyan]4[/] Force Proton version for an AppID")
        console.print("  [cyan]5[/] Clear forced options for an AppID")
        console.print("  [cyan]0[/] Back to main menu")
        console.print()

        choice = Prompt.ask(
            "[bold]Select an option[/]",
            choices=["0", "1", "2", "3", "4", "5"],
            default="0",
        )

        if choice == "0":
            break
        elif choice == "1":
            app_id = Prompt.ask("[bold]Enter AppID to exclude[/]")
            if add_exclusion(app_id):
                _print_success(f"Excluded {app_id}")
            else:
                _print_error("Failed to add exclusion")
        elif choice == "2":
            app_id = Prompt.ask("[bold]Enter AppID to un-exclude[/]")
            if remove_exclusion(app_id):
                _print_success(f"Removed exclusion for {app_id}")
            else:
                _print_error("Failed to remove exclusion")
        elif choice == "3":
            app_id = Prompt.ask("[bold]Enter AppID[/]")
            opts = Prompt.ask("[bold]Launch options to force (enter raw string)[/]")
            if set_forced_options(app_id, opts):
                _print_success(f"Forced options set for {app_id}")
            else:
                _print_error("Failed to set forced options")
        elif choice == "4":
            app_id = Prompt.ask("[bold]Enter AppID[/]")
            # List available Proton versions
            protons = scan_proton_versions()
            if protons:
                console.print("\n[bold]Available Proton versions:[/]")
                for pv in protons:
                    console.print(f"  {pv.name}")
                console.print()
            pname = Prompt.ask("[bold]Proton version name[/]")
            if set_forced_proton(app_id, pname):
                _print_success(f"Forced Proton set for {app_id}")
            else:
                _print_error("Failed to set forced Proton")
        elif choice == "5":
            app_id = Prompt.ask("[bold]Enter AppID to clear forced options for[/]")
            # Clear both
            ok1 = set_forced_options(app_id, "")
            ok2 = set_forced_proton(app_id, "")
            if ok1 and ok2:
                _print_success(f"Cleared forced settings for {app_id}")
            elif ok1 or ok2:
                cleared = "options" if ok1 else "Proton"
                _print_warning(f"Only cleared forced {cleared} for {app_id}")
            else:
                _print_error("Failed to clear forced settings")

        _wait_for_enter()


def _settings_menu() -> None:
    """Menu option 7: settings management."""
    while True:
        _print_header("Settings")
        settings = load_settings()

        table = Table(box=box.SQUARE)
        table.add_column("#", style="bold cyan", width=3)
        table.add_column("Setting")
        table.add_column("Value", style="bold yellow")

        items = [
            ("1", "Max backups to keep", str(settings.get("max_backups", 20))),
            ("2", "Min reports for recommendation", str(settings.get("min_reports_for_recommendation", 3))),
            ("3", "Confidence threshold", f"{settings.get('confidence_threshold', 0.3):.0%}"),
        ]
        for num, label, val in items:
            table.add_row(num, label, val)

        console.print(table)
        console.print("  [cyan]0[/] Back to main menu")
        console.print()

        choice = Prompt.ask(
            "[bold]Select a setting to change[/]",
            choices=["0", "1", "2", "3"],
            default="0",
        )

        if choice == "0":
            break
        elif choice == "1":
            val = IntPrompt.ask("[bold]Max backups[/]", default=20)
            update_setting("max_backups", max(1, val))
            _print_success(f"max_backups set to {max(1, val)}")
        elif choice == "2":
            val = IntPrompt.ask("[bold]Min reports[/]", default=3)
            update_setting("min_reports_for_recommendation", max(1, val))
            _print_success(f"min_reports set to {max(1, val)}")
        elif choice == "3":
            val = Prompt.ask("[bold]Confidence threshold (0.0 - 1.0)[/]", default="0.3")
            try:
                fval = float(val)
                update_setting("confidence_threshold", max(0.0, min(1.0, fval)))
                _print_success(f"confidence_threshold set to {max(0.0, min(1.0, fval)):.0%}")
            except ValueError:
                _print_error("Invalid number")

        _wait_for_enter()


# ─── Main Loop ──────────────────────────────────────────────────────────────

def main() -> None:
    """Run the ProtonTune interactive CLI."""
    ensure_config_dir()

    # Quick check: whether we're in a terminal
    if not sys.stdout.isatty():
        _err.print("ProtonTune requires an interactive terminal.")
        sys.exit(1)

    while True:
        try:
            choice = _show_home_menu()
            if choice == 0:
                console.print("\n[bold cyan]Goodbye![/] 🎮\n")
                break
            elif choice == 1:
                _scan_library_and_hardware()
            elif choice == 2:
                _view_recommendations()
            elif choice == 3:
                _apply_optimizations()
            elif choice == 4:
                _restore_backup()
            elif choice == 5:
                _refresh_protondb_data()
            elif choice == 6:
                _manage_exceptions()
            elif choice == 7:
                _settings_menu()
        except KeyboardInterrupt:
            console.print("\n\n[bold yellow]Interrupted. Exiting.[/]")
            break
        except Exception as e:
            _print_error(f"Unexpected error: {e}")
            console.print(f"\n[dim]{traceback.format_exc()}[/]")
            _wait_for_enter()


if __name__ == "__main__":
    main()
