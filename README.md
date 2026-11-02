# animepahe-jellyfin-renamer

A batch renamer (`rename_episodes.py`) that appends Jellyfin-style `SxxEyy` tags to AnimePahe episode files, so your media server can match them to the right season and episode.

```
AnimePahe_Kono_Subarashii_Sekai_ni_Shukufuku_wo_2_-_01_BD_720p_Chihiro.mkv
        ->
AnimePahe_Kono_Subarashii_Sekai_ni_Shukufuku_wo_2_-_01_BD_720p_Chihiro S02E01.mkv
```

The original filename is never modified. The script only appends ` SxxEyy` before the file extension.

## Requirements

- Python 3.10 or newer (no third-party packages)

## Installation

```bash
git clone https://github.com/tomasArd25/Animepahe-Batch-Rename-for-Jellyfin.git
cd Animepahe-Batch-Rename-for-Jellyfin
```

There is nothing to install. Just run `rename_episodes.py` with Python.

## Quick start

Always preview first with `--dry-run`, then run again without it to apply.

```bash
# Preview
python rename_episodes.py "\\192.168.10.2\jellyfin_contents\anime" --dry-run

# Apply
python rename_episodes.py "\\192.168.10.2\jellyfin_contents\anime"
```

## What you can point it at

The script recursively searches for folders named `Season XX` at any depth, so you can point it at any level:

| Path you give | What happens |
|---|---|
| `.../anime` (whole library) | Every show, every `Season XX` folder |
| `.../anime/Hataraku Saibou` (one show) | All `Season XX` folders in that show |
| `.../anime/Kekkai Sensen/Season 02` (one season) | Just that season |

Folders that don't match `Season XX` (for example `Extras`) are never touched. Once it finds a `Season XX` folder, it stops descending into it.

## Expected folder layout

```
anime/
  Show Name/
    Season 01/
    Season 02/
    Season 00/      <- specials, skipped by default
```

The season number comes from the folder name (`Season 02` becomes `S02`). Spacing and case don't matter (`season_2` also works).

## How episode numbers are worked out

Files are expected to follow the AnimePahe naming convention, where the episode number sits right after a `-_`:

```
AnimePahe_Show_Title_-_09_720p_SubsPlease.mkv
                      ^^^^
```

- Requiring the `-_` prefix stops numbers inside the show title (like the `2` in `Shukufuku_wo_2_-_01`) from being mistaken for the episode.
- Release-version tags such as `01v2` or `03v3` are recognised and ignored for numbering. The original name, `v2` included, is kept.

### Mapping to E01

Release numbering doesn't always restart per season. If a season's files start at `09`, that file should become `E01`. For each season folder, the starting point is chosen in this order:

1. `--start-episode N`, if you pass it.
2. Recovered from files already renamed in that folder. Because the raw number is kept in the name, `..._-_11_... S01E11` tells the script the mapping is `raw - episode + 1 = 1`. This lets you add a forgotten episode later and have it land on the correct number.
3. The lowest episode number found in the folder, which becomes `E01`.

Example with files `09`, `10`, `11` in `Season 02`: they become `S02E01`, `S02E02`, `S02E03`.

## Safety features

- **Dry run:** `--dry-run` prints what would change and renames nothing.
- **Source tag filter:** only files whose name contains `AnimePahe` (case-insensitive) are touched. Everything else is skipped and logged.
- **Already-renamed detection:** files already ending in an `SxxEyy` tag are skipped, so re-running never double-tags.
- **No overwrites:** if the target name already exists, the file is skipped with a warning.
- **Specials skipped:** `Season 00` folders are skipped by default.
- **No hidden files:** nothing is stored on disk. Everything is derived from the filenames on each run.

## Options

| Option | Description |
|---|---|
| `folder` | Season folder, show folder, or whole library folder |
| `--dry-run` | Preview changes without renaming |
| `--exclude TEXT` | Skip any season folder whose path contains `TEXT` (case-insensitive). Repeatable |
| `--include-specials` | Also process `Season 00` folders |
| `--season N` | Override the season number. Only applies when exactly one season folder is found |
| `--start-episode N` | Treat raw episode `N` as `E01` instead of auto-detecting |
| `--require-tag TEXT` | Only rename files containing `TEXT` (default: `AnimePahe`) |
| `--no-tag-filter` | Disable the source tag filter entirely |

## Examples

```bash
# Whole library, skipping two shows
python rename_episodes.py "\\192.168.10.2\jellyfin_contents\anime" --exclude "UQ Holder" --exclude "Kekkai Sensen" --dry-run

# One season, forcing the starting episode
python rename_episodes.py "/path/to/Show/Season 02" --start-episode 9 --dry-run

# Different release group
python rename_episodes.py "/path/to/anime" --require-tag SubsPlease --dry-run

# Include specials
python rename_episodes.py "/path/to/Show" --include-specials --dry-run
```

## Output messages

| Tag | Meaning |
|---|---|
| `[DRY RUN]` | Would be renamed (preview only) |
| `[RENAMED]` | Renamed |
| `[SKIP]` | Skipped (missing source tag, already renamed, no episode number, or a specials folder) |
| `[EXCLUDE]` | Season folder skipped by `--exclude` |
| `[WARN]` | Something needs attention, such as a target name that already exists |
| `[ERROR]` | A folder couldn't be processed |
| `[INFO]` | Detection details (season, starting episode) |

## Troubleshooting

- **Windows paths ending in a backslash:** a trailing `\` before the closing quote can break the argument (`"C:\anime\"`). Leave the trailing backslash off.
- **Wrong episode numbers:** run with `--dry-run` and check the `[INFO]` line for the detected starting episode. Override it with `--start-episode` if needed.
- **Nothing happens:** make sure the folders are named `Season XX` and the filenames contain `AnimePahe` and a `-_NN_` episode segment.
- **Different filename style:** the episode pattern is `EPISODE_PATTERN` near the top of the script.
