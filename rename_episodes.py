#!/usr/bin/env python3
"""
Batch-renames files like:
  AnimePahe_Arknights_-_Reimei_Zensou_-_01_720p_SubsPlease
to:
  AnimePahe_Arknights_-_Reimei_Zensou_-_720p_SubsPlease S01E01

Usage:
  1. Run with --dry-run first to preview changes.
  2. Run without --dry-run to actually rename.

  Point this at ANY of the following, and it figures out the rest:
    - A single season folder:      ".../Kekkai Sensen/Season 02"
    - A show's root folder:        ".../Hataraku Saibou"      (has Season XX subfolders)
    - Your whole anime library:    ".../anime"                (has show subfolders, each with Season XX)

  It recursively looks for folders named "Season XX" at any depth and
  processes each independently, auto-detecting:
    - The season number, from the "Season XX" folder name itself
    - The starting episode number, either recovered from files already
      renamed in that folder, or auto-detected as the lowest episode number
      found there if nothing's been renamed yet -- no hidden state files
      are used or needed.
    - It only touches files whose name contains "AnimePahe" (case-insensitive),
      as a failsafe so unrelated files are never renamed.

  Override auto-detected values with --season / --start-episode if needed
  (only makes sense when pointing at a single season folder).
  Change or disable the safety filter with --require-tag / --no-tag-filter.

  python rename_episodes.py "\\\\192.168.10.2\\jellyfin_contents\\anime" --dry-run
  python rename_episodes.py "\\\\192.168.10.2\\jellyfin_contents\\anime\\Hataraku Saibou" --dry-run
  python rename_episodes.py "\\\\192.168.10.2\\jellyfin_contents\\anime\\Kekkai Sensen\\Season 02" --dry-run
  python rename_episodes.py "/path/to/folder" --season 2 --start-episode 9
  python rename_episodes.py "/path/to/folder" --require-tag SubsPlease
  python rename_episodes.py "/path/to/folder" --no-tag-filter
"""

import os
import re
import argparse

# Matches an episode number like "_01_" or "_12_", but only when it's the
# "-_NN_" segment that follows the show title (the usual release convention),
# so numbers embedded in the show's own title (e.g. "...Shukufuku_wo_2_-_...")
# aren't mistaken for the episode number. Also allows an optional release-
# version tag like "v2" or "v3" right after the number (e.g. "-_01v2_" for a
# re-uploaded/re-encoded episode) -- the version tag is captured but ignored.
EPISODE_PATTERN = re.compile(r"-_(\d{1,3})(?:v\d+)?_")

# Matches "Season 02", "season2", "Season_02", etc. anywhere in a path component
SEASON_PATTERN = re.compile(r"season[\s_-]*0*(\d{1,3})", re.IGNORECASE)

# Matches an already-appended "SxxEyy" tag, so files that were already
# renamed by this script don't get the tag appended a second time.
ALREADY_RENAMED_PATTERN = re.compile(r"\sS\d{2}E\d{2,3}(?=\.[^.]*$|$)", re.IGNORECASE)

# Default failsafe: only rename files whose name contains this tag
DEFAULT_REQUIRED_TAG = "AnimePahe"


def has_required_tag(filename: str, required_tag: str | None) -> bool:
    """
    Returns True if required_tag is None (filter disabled) or the tag is
    found in the filename (case-insensitive).
    """
    if not required_tag:
        return True
    return required_tag.lower() in filename.lower()


def detect_season_from_path(folder: str) -> int | None:
    """
    Scans the full folder path (all components, deepest first) for a
    "Season XX" pattern and returns the number if found, e.g.
    ".../Season 02" -> 2.
    """
    normalized = folder.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p]
    for part in reversed(parts):
        match = SEASON_PATTERN.search(part)
        if match:
            return int(match.group(1))
    return None


def find_all_season_folders(root: str) -> list[tuple[int, str]]:
    """
    Recursively searches under `root` for folders named "Season XX", at any
    depth -- the root itself, a show folder inside it, a whole library
    folder containing many shows, etc.

    Stops descending as soon as a "Season XX" folder is found along a given
    branch (season folders aren't expected to contain further season
    folders), so folders like "Specials" or a show's own root are simply
    skipped rather than mis-processed.

    Returns a sorted list of (season_number, full_folder_path) tuples.
    """
    normalized_root = os.path.normpath(root)
    root_name = os.path.basename(normalized_root)

    # If the given root itself is a "Season XX" folder, use it directly.
    match = SEASON_PATTERN.search(root_name)
    if match:
        return [(int(match.group(1)), normalized_root)]

    results = []
    try:
        entries = sorted(os.listdir(normalized_root))
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        print(f"[ERROR] Could not read folder {normalized_root}: {e}")
        return results

    for entry in entries:
        full_path = os.path.join(normalized_root, entry)
        if not os.path.isdir(full_path):
            continue

        sub_match = SEASON_PATTERN.search(entry)
        if sub_match:
            results.append((int(sub_match.group(1)), full_path))
        else:
            # Not a season folder itself (could be a show folder, a library
            # folder, "Specials", etc.) -- keep looking deeper.
            results.extend(find_all_season_folders(full_path))

    results.sort(key=lambda x: (x[1], x[0]))
    return results


def detect_anchor_from_renamed(folder: str, season: int, required_tag: str | None) -> int | None:
    """
    Looks for files that are already renamed (have both the original raw
    "-_NN_" episode marker AND an appended "SxxEyy" tag for this season) and
    recovers the exact start_episode anchor that must have been used:
    raw_episode - assigned_episode + 1.

    If multiple already-renamed files are found and they don't agree on the
    same anchor, returns None and lets the caller fall back / warn, since
    something inconsistent is going on.
    """
    tag_pattern = re.compile(rf"S{season:02d}E(\d{{2,3}})", re.IGNORECASE)
    anchors = set()

    for filename in os.listdir(folder):
        if not has_required_tag(filename, required_tag):
            continue

        ep_match = EPISODE_PATTERN.search(filename)
        tag_match = tag_pattern.search(filename)
        if ep_match and tag_match:
            raw = int(ep_match.group(1))
            assigned = int(tag_match.group(1))
            anchors.add(raw - assigned + 1)

    if len(anchors) == 1:
        return anchors.pop()
    if len(anchors) > 1:
        print(f"[WARN] Already-renamed files in {folder} don't agree on a single "
              f"starting episode mapping ({sorted(anchors)}); ignoring them for "
              f"auto-detection.")
    return None


def detect_lowest_episode(folder: str, required_tag: str | None) -> int | None:
    """
    Scans the folder and returns the lowest episode number found among
    files matching EPISODE_PATTERN, restricted to files that pass the
    required_tag filter. Returns None if no matches.
    """
    lowest = None
    for filename in os.listdir(folder):
        full_path = os.path.join(folder, filename)
        if not os.path.isfile(full_path):
            continue

        if not has_required_tag(filename, required_tag):
            continue

        name, _ = os.path.splitext(filename)
        match = EPISODE_PATTERN.search(name)
        if match:
            num = int(match.group(1))
            if lowest is None or num < lowest:
                lowest = num

    return lowest


def build_new_name(filename: str, season: int, start_episode: int = 1) -> str | None:
    """
    Returns the new filename, or None if no episode number pattern was found.
    Keeps the file extension intact if present.

    The original filename is left untouched -- the "_NN_" episode marker
    stays exactly where it was. Only a " SxxEyy" tag is appended before the
    extension.

    start_episode: the filename episode number that should be treated as E01.
    e.g. if start_episode=9, then file episode 09 -> E01, 10 -> E02, etc.
    """
    name, ext = os.path.splitext(filename)

    match = EPISODE_PATTERN.search(name)
    if not match:
        return None

    file_episode_num = int(match.group(1))
    episode_num = file_episode_num - start_episode + 1

    if episode_num < 1:
        print(f"[WARN] Computed episode number < 1 for {filename} "
              f"(file ep {file_episode_num}, start {start_episode}), skipping.")
        return None

    # Original filename is left completely intact -- just append the tag.
    new_name = f"{name} S{season:02d}E{episode_num:02d}{ext}"
    return new_name


def rename_files(folder: str, season: int, dry_run: bool = True,
                  start_episode: int = 1, required_tag: str | None = DEFAULT_REQUIRED_TAG) -> int:
    files = sorted(os.listdir(folder))
    renamed_count = 0

    for filename in files:
        full_path = os.path.join(folder, filename)
        if not os.path.isfile(full_path):
            continue

        if not has_required_tag(filename, required_tag):
            print(f"[SKIP] Missing required tag '{required_tag}': {filename}")
            continue

        if ALREADY_RENAMED_PATTERN.search(filename):
            print(f"[SKIP] Already renamed: {filename}")
            continue

        new_name = build_new_name(filename, season, start_episode)
        if new_name is None:
            print(f"[SKIP] No episode number found: {filename}")
            continue

        new_path = os.path.join(folder, new_name)

        if dry_run:
            print(f"[DRY RUN] {filename}\n       -> {new_name}\n")
        else:
            if os.path.exists(new_path):
                print(f"[WARN] Target already exists, skipping: {new_name}")
                continue
            os.rename(full_path, new_path)
            print(f"[RENAMED] {filename}\n       -> {new_name}\n")

        renamed_count += 1

    print(f"Done with this folder. {renamed_count} file(s) {'would be' if dry_run else ''} renamed.\n")
    return renamed_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch rename episode files.")
    parser.add_argument("folder", help="Path to the folder containing the files, OR a show's "
                                        "root folder containing Season XX subfolders.")
    parser.add_argument("--season", type=int, default=None,
                         help="Season number. If omitted, it is auto-detected from the "
                              "folder path (e.g. '.../Season 02' -> 2). Ignored if the "
                              "given folder contains multiple Season XX subfolders.")
    parser.add_argument("--start-episode", type=int, default=None,
                         help="The filename's episode number that should map to E01. "
                              "If omitted, it is auto-detected per-folder as the lowest "
                              "episode number found there.")
    parser.add_argument("--require-tag", type=str, default=DEFAULT_REQUIRED_TAG,
                         help=f"Only rename files whose name contains this tag "
                              f"(case-insensitive). Default: '{DEFAULT_REQUIRED_TAG}'.")
    parser.add_argument("--no-tag-filter", action="store_true",
                         help="Disable the tag filter entirely (rename any file with an "
                              "episode number, regardless of source tag).")
    parser.add_argument("--exclude", type=str, action="append", default=[],
                         help="Skip any season folder whose path contains this text "
                              "(case-insensitive), e.g. --exclude \"UQ Holder\". Can be "
                              "given multiple times to exclude several shows.")
    parser.add_argument("--include-specials", action="store_true",
                         help="By default, 'Season 00' folders (specials, per Jellyfin "
                              "convention) are skipped, since specials often have irregular "
                              "numbering that needs manual review. Pass this to process them "
                              "like any other season.")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without renaming")

    args = parser.parse_args()

    required_tag = None if args.no_tag_filter else args.require_tag

    def process_single_folder(folder: str, season_override, start_ep_override) -> int:
        """Handles one folder that directly contains episode files."""
        season = season_override
        if season is None:
            detected_season = detect_season_from_path(folder)
            if detected_season is None:
                print(f"[ERROR] Could not detect a season number from the folder path "
                      f"(expected something like 'Season 02') for: {folder}")
                return 0
            season = detected_season
            print(f"[INFO] Auto-detected season from path: Season {season:02d}")

        start_episode = start_ep_override
        if start_episode is None:
            anchor = detect_anchor_from_renamed(folder, season, required_tag)
            if anchor is not None:
                start_episode = anchor
                print(f"[INFO] Recovered starting episode from already-renamed files: "
                      f"{start_episode:02d} -> maps to E01")
            else:
                detected = detect_lowest_episode(folder, required_tag)
                if detected is None:
                    print(f"[ERROR] Could not detect any matching episode files in folder: {folder}")
                    return 0
                start_episode = detected
                print(f"[INFO] Auto-detected lowest episode number: {start_episode:02d} -> will map to E01")

        return rename_files(folder, season, args.dry_run, start_episode, required_tag)

    if required_tag:
        print(f"[INFO] Safety filter active: only renaming files containing '{required_tag}'\n")
    else:
        print("[INFO] Safety filter disabled: all files with an episode number will be renamed\n")

    # Recursively find every "Season XX" folder under the given path -- this
    # naturally covers a single season folder, a show's root folder, or a
    # whole library folder containing many shows.
    season_folders = find_all_season_folders(args.folder)

    if not args.include_specials:
        kept = []
        for season_num, subfolder in season_folders:
            if season_num == 0:
                print(f"[SKIP] Specials (Season 00), pass --include-specials to process: {subfolder}")
            else:
                kept.append((season_num, subfolder))
        season_folders = kept
        print()

    if args.exclude:
        excluded_terms = [term.lower() for term in args.exclude]
        kept = []
        for season_num, subfolder in season_folders:
            path_lower = subfolder.lower()
            if any(term in path_lower for term in excluded_terms):
                print(f"[EXCLUDE] Skipping: {subfolder}")
            else:
                kept.append((season_num, subfolder))
        season_folders = kept
        print()

    if not season_folders:
        print(f"[ERROR] No 'Season XX' folders found under: {args.folder}")
        raise SystemExit(1)

    print(f"[INFO] Found {len(season_folders)} season folder(s) under: {args.folder}\n")

    # --season only makes sense as an override when there's a single,
    # unambiguous season folder being processed.
    season_override = args.season if len(season_folders) == 1 else None
    if args.season is not None and len(season_folders) > 1:
        print("[WARN] --season is ignored when multiple season folders are found; "
              "each folder uses its own detected season number.\n")

    total_renamed = 0
    for season_num, subfolder in season_folders:
        print(f"=== Season {season_num:02d}: {subfolder} ===")
        total_renamed += process_single_folder(subfolder, season_override or season_num, args.start_episode)
        print()

    print(f"All done. {total_renamed} file(s) {'would be' if args.dry_run else ''} renamed in total.")