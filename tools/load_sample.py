#!/usr/bin/env python3
"""Copy the sample board data into a folder, with every date moved so the sample day is today.

  python3 tools/load_sample.py <destination folder> [--date YYYY-MM-DD] [--no-shift]

The sample was written for one invented day (the date in sample/state/brief-today.json). The page shows a
brief only on its own day, so this script moves every date in the copy by the same number of days: task
dates, note dates, card dates, the brief and the meeting file names. --date picks another target day than
today; --no-shift copies the files as they are. The destination must not already hold a tasks.md, summaries, cards, files in meetings/ or a state/brief-today.json.
"""
import json, re, shutil, subprocess, sys
from datetime import date, timedelta
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
SAMPLE = KIT / "sample"
DAY = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")


def shifter(days):
    def move(m):
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return m.group(0)
        return (d + timedelta(days=days)).isoformat()
    return lambda text: DAY.sub(move, text)


def copy_sample(dest, target=None, shift=True):
    """Copy sample/ to dest. Returns the number of days every date was moved by."""
    dest = Path(dest)
    if not SAMPLE.is_dir():
        sys.exit(f"no sample folder beside this script ({SAMPLE}); run the copy of load_sample.py that is inside the kit")
    for name in ("tasks.md", "summaries", "state/confirm-queue"):
        there = dest / name
        if there.is_file() or (there.is_dir() and any(there.iterdir())):
            sys.exit(f"{dest} already holds {name}; nothing was copied. The sample goes into a board folder that has no tasks yet.")
    meetings = dest / "meetings"
    if meetings.is_dir() and any(meetings.iterdir()):
        sys.exit(f"{dest} already holds files in meetings/; nothing was copied. The sample would mix with your notes.")
    if (dest / "state" / "brief-today.json").exists():
        sys.exit(f"{dest} already holds state/brief-today.json; nothing was copied. The sample would replace your brief.")
    base = date.fromisoformat(json.loads((SAMPLE / "state" / "brief-today.json").read_text(encoding="utf-8-sig"))["date"])
    days = ((target or date.today()) - base).days if shift else 0
    move = shifter(days)
    for src in sorted(SAMPLE.rglob("*")):
        if src.is_dir() or src.name.startswith(".") or "out" in src.relative_to(SAMPLE).parts:
            continue
        if src.name == "README.md":
            continue   # an index of the kit's sample folder, not sample data
        out = dest / move(src.relative_to(SAMPLE).as_posix())
        if src.name == "board.config.json" and out.exists():
            continue   # the folder already has its own config; keep it
        if src.name == "sweep-sources.json":
            continue   # a shape to copy from, with placeholder ids; the setup writes the real one
        if src.name == "setup.json":
            continue   # the sample's own setup state; a real board writes its own
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes((move(src.read_text(encoding="utf-8-sig"))).encode("utf-8"))
    if days:  # the notes changed, so record again that each summary matches its notes
        ids = sorted(p.stem for p in (dest / "summaries").glob("T*.json"))
        subprocess.run([sys.executable, str(KIT / "board" / "sync_tasks.py"), "--config", str(dest / "board.config.json"), "stamp", *ids],
                       check=True, stdout=subprocess.DEVNULL)
    return days


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or "-h" in args or "--help" in args:
        print(__doc__)
        sys.exit(0 if args else 1)
    target = None
    if "--date" in args:
        i = args.index("--date")
        try:
            target = date.fromisoformat(args[i + 1])
        except (IndexError, ValueError):
            sys.exit("--date needs a day written as YYYY-MM-DD")
        del args[i:i + 2]
    shift = "--no-shift" not in args
    places = [a for a in args if not a.startswith("--")]
    if len(places) != 1:
        sys.exit("give exactly one destination folder; see --help")
    moved = copy_sample(places[0], target, shift)
    print(f"sample copied to {places[0]}; every date moved by {moved} days")
