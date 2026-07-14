# ProtonTune 🎮

**Optimize your Steam games on Linux with ProtonDB-powered recommendations.**

ProtonTune is an interactive, menu-driven CLI tool that analyzes your installed
Steam library and hardware, cross-references ProtonDB community data, and helps
you configure the best Proton version and launch options per game — **safely**,
with automatic backups and explicit user confirmation before every change.

---

## Features

- 🔍 **Hardware detection** — automatically identifies your GPU vendor and model
  to tailor recommendations (NVIDIA, AMD, Intel).
- 📚 **Steam library scanning** — detects installed games from all Steam
  installation methods (native, Flatpak, Snap) without needing Steam to run.
- 🧪 **Proton version inventory** — scans for official Valve Proton builds and
  custom builds (GE-Proton, Proton-GE, etc.).
- 📊 **ProtonDB integration** — uses the official [ProtonDB data dump]
  (https://github.com/bdefore/protondb-data) (ODbL-licensed) to score and
  recommend launch options per game. Downloaded and extracted automatically
  from GitHub — no API keys or live endpoints needed.
- 🧠 **Frequency-based scoring** — only launch options used by ≥3% of
  community reports are recommended. Noisy or hardware-specific options
  (GPU model names, driver paths, audio server choices, etc.) are
  automatically filtered out. `gamemoderun %command%` is always appended.
- 🎯 **Per-game workflow** — scan your library once, then pick individual
  games to view recommendations or apply optimisations.
- 💾 **Automatic backups** — every modification creates a timestamped backup of
  your Steam configuration files, with configurable retention.
- 🔄 **Restore** — roll back to any previous backup from the interactive menu.
- 🚫 **Per-game exceptions** — exclude specific games or force custom launch
  options via a version-control-friendly YAML file.
- ⚙️ **Settings** — configurable thresholds for confidence, report minimums,
  and backup retention.

## Installation

### Prerequisites

- **Python 3.10+**
- **pip** or **pipx**

### Install via pip

```bash
pip install protontune
```

### Install via pipx (recommended for isolated installation)

```bash
pipx install protontune
```

### Install from source

```bash
git clone https://github.com/hsh/Protontune.git
cd Protontune
pip install .
```

## Usage

Run ProtonTune from your terminal:

```bash
protontune
```

This launches the interactive menu:

```
╔════════════════════════╗
║ ProtonTune v0.1.0      ║
║ Steam Proton Optimizer ║
╚════════════════════════╝

 1  Scan library & hardware
 2  View recommendations (dry-run, no changes)
 3  Apply optimizations (creates a backup automatically)
 4  Restore a previous backup
 5  Refresh local ProtonDB data
 6  Manage per-game exceptions
 7  Settings
 0  Exit
```

### Typical workflow

```
1. Scan library & hardware    ← detects GPU, Steam games, Proton builds
2. Select games               ← pick one or more games from the list
3. View recommendations       ← see proposed Proton version + launch options
4. Apply optimizations        ← backup is created, changes written
5. Start Steam and play! 🎮
```

### First-time setup

1. **Scan your system** — select option **1** to detect your GPU, Steam
   library, and installed Proton versions.
2. **Download ProtonDB data** — select option **5**, then option **1** to
   automatically download the latest data dump from GitHub (~60 MB).
   Alternatively, download manually from
   [github.com/bdefore/protondb-data](https://github.com/bdefore/protondb-data/tree/master/reports)
   and extract to `~/.config/steam-proton-optimizer/data/`.
3. **Preview recommendations** — select option **2**, pick a game, and see
   what Proton version and launch options are suggested.
4. **Apply optimisations** — select option **3**, pick the same game, confirm
   the changes. A backup is created automatically first.

> **⚠️ Steam must be fully closed before applying changes.**
> ProtonTune checks for running Steam processes and will refuse to write if
> Steam is detected.

## How It Works

### Data Flow

```
ProtonDB Data Dump (local)
         │
         ▼
┌────────────────┐     ┌──────────────────┐
│  Steam Library  │────▶│  Scanning        │
│  Scan           │     │  & Hardware      │
└────────────────┘     │  Detection       │
                        └────────┬─────────┘
┌────────────────┐              │
│  Proton        │              │
│  Installation  │──────────────┘
└────────────────┘              ▼
                        ┌────────────────┐
                        │  Game Selector  │────▶ Pick one or more games
                        └────────┬─────────┘
                                 │
                                 ▼
                        ┌────────────────┐
                        │  Scoring        │
                        │  Engine         │
                        │  (frequency     │
                        │   ≥ 3%)         │
                        └────────┬─────────┘
                                 │
                                 ▼
                        ┌────────────────┐
                        │  Preview / Diff │────▶ Show proposed changes
                        └────────┬─────────┘
                                 │
                                 ▼
                        ┌────────────────┐
                        │  Backup &      │
                        │  Apply         │
                        └────────────────┘
```

### Scoring Model

Launch options are scored by **raw frequency** — the proportion of
Gold/Platinum community reports that use a specific option:

```
score(option) = count(option) / total_reports
```

- Only options with **≥3% frequency** are included in the recommendation.
- Hardware-specific noise (GPU model names, driver paths, audio servers,
  keyboard layouts, etc.) is automatically filtered out.
- Cosmetic overlays (`MANGOHUD=1`) are excluded — they don't affect
  game compatibility.
- `gamemoderun %command%` is always appended to the final launch string.
- Mutually exclusive options (e.g. `DXVK_ASYNC` vs `PROTON_USE_WINED3D`)
  are resolved — only the highest-scored option in each conflict group is kept.

This approach ensures recommendations are **conservative and generalisable**:
only options that a meaningful number of users actually needed.

### Safety

- **Steam must be closed** — the tool refuses to write if Steam is running.
- **Backups first** — every modification is preceded by a full backup of
  `config.vdf` and `localconfig.vdf`.
- **Confirmation required** — a diff preview is always shown and must be
  explicitly confirmed before any changes are written.
- **No auto-install** — missing Proton versions are reported with a fallback,
  never downloaded automatically.

## Configuration

### Per-Game Exceptions

Edit `~/.config/steam-proton-optimizer/exceptions.yaml` manually or use menu
option 6:

```yaml
exclude:
  - "123456"          # Never modify this game
force_options:
  "789012": "DXVK_ASYNC=1 %command%"
force_proton:
  "345678": "GE-Proton9-25"
```

### Settings

Accessible via menu option 7 or at `~/.config/steam-proton-optimizer/settings.yaml`:

| Setting | Default | Description |
|---|---|---|
| `max_backups` | 20 | Number of backups to retain |
| `min_reports_for_recommendation` | 3 | Minimum ProtonDB reports needed |
| `confidence_threshold` | 0.3 | Minimum confidence (0.0–1.0) to apply |

## Project Status

ProtonTune is in **alpha**. The core scanning, scoring, and configuration
injection are functional. Breaking changes may occur as the project matures.

### Roadmap

- [x] Hardware detection
- [x] Steam library scanning
- [x] Proton version inventory
- [x] ProtonDB data import (GitHub dump — flat JSON array)
- [x] Frequency-based scoring engine with noise filtering
- [x] Per-game interactive workflow
- [x] Backup and restore
- [x] Per-game exceptions
- [ ] Integration tests with real ProtonDB dumps
- [ ] More advanced conflict resolution
- [ ] Support for per-game environment variables

### Out of Scope

- Steam Deck-specific handling
- Live ProtonDB API calls or scraping undocumented endpoints
- Automatic download/installation of missing Proton builds
- Background or scheduled execution

## License

MIT — see [LICENSE](LICENSE).

The ProtonDB data dump is provided under the [Open Database License (ODbL)]
(https://opendatacommons.org/licenses/odbl/). You must download and manage
this data yourself.
