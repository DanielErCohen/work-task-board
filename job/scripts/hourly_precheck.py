#!/usr/bin/env python3
"""Cheap first step of the hourly board job, so an hour with nothing new stops early.

  hourly_precheck.py start            take the run lock and print what the run needs to know (JSON), or BUSY
  hourly_precheck.py seen <id> ...    print the source IDs (a document ID, a file name) that are not filed yet, one per line
  hourly_precheck.py filed <id> <note-file>   record that a source was filed as that note
  hourly_precheck.py finish           record the run and release the lock (--brief: brief written, --sweep: mail and chat swept,
                                      --review: weekly review written)
  hourly_precheck.py board-wait       note that a board write is about to wait for the owner's approval
  hourly_precheck.py board-done       clear that note after the board write succeeded

State lives in the folder named by "state" in board.config.json (default: state/): run.lock, hourly-run.json,
processed.json, confirm-queue/ and run-log.jsonl (one line per finished run, read by efficiency_report.py).
Three more keys of board.config.json are read here: "sweeps" (false when neither mail nor chat is swept),
"sweep_hours" (default [8, 14]) and "weekly_review" (false when the weekly review is off). When one is off,
`start` reports it as not due, so a quiet hour still stops early.
The config file is looked for in this order: --config <path>, the BOARD_CONFIG environment variable, the
current folder, then the folder of this script and its parents.
"""
import json, os, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

STALE_SECONDS = 45 * 60        # a lock older than this belongs to a run that died
BOARD_WAIT_SECONDS = 3 * 3600  # a board write waiting for approval blocks further attempts this long


def config():
    args = sys.argv[1:]
    explicit = args[args.index("--config") + 1] if "--config" in args and args.index("--config") + 1 < len(args) else os.environ.get("BOARD_CONFIG")
    here = Path(__file__).resolve().parent
    path = Path(explicit) if explicit else next((f / "board.config.json" for f in [Path.cwd(), here, *here.parents] if (f / "board.config.json").exists()), None)
    if not path or not path.exists():
        sys.exit("No board.config.json found. Run from the folder that holds it, or pass --config <path>.")
    try:
        cfg = json.loads(path.read_text())
    except ValueError:
        print(f"{path}: not valid JSON", file=sys.stderr)
        sys.exit(2)
    return cfg, path.resolve().parent / cfg.get("state", "state")


if any(a in ("--help", "-h") for a in sys.argv[1:]):   # help needs no board folder
    print(__doc__)
    sys.exit(0)
CFG, STATE = config()
LOCK = STATE / "run.lock"
RUN = STATE / "hourly-run.json"
# Local hours; the first run at or after each one sweeps mail and chat. No hours when sweeps are switched off.
_HOURS = CFG.get("sweep_hours", [8, 14])
if not (isinstance(_HOURS, list) and all(isinstance(h, int) and not isinstance(h, bool) for h in _HOURS)):
    sys.exit('board.config.json: "sweep_hours" must be a list of whole numbers, for example [8, 14]')
SWEEP_HOURS = tuple(_HOURS) if CFG.get("sweeps", True) else ()


def load(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def parse(ts):
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def sweep_state(run):
    """(due, since): due when a sweep hour has passed today with no sweep after it."""
    now = datetime.now().astimezone()
    last = parse(run.get("last_sweep_at"))
    since = last or (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    passed = [h for h in SWEEP_HOURS if now.hour >= h]
    if not passed:
        return False, since
    boundary = now.replace(hour=max(passed), minute=0, second=0, microsecond=0)
    return (last is None or last < boundary), since


def iso_week():
    y, w, _ = date.today().isocalendar()
    return f"{y}-W{w:02d}"


def start():
    (STATE / "confirm-queue").mkdir(parents=True, exist_ok=True)
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime >= STALE_SECONDS:
        LOCK.unlink(missing_ok=True)   # a run that died
    try:   # created only if it does not exist, so two runs starting together cannot both take it
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print("BUSY")
        return
    with os.fdopen(fd, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())
    run = load(RUN, {})
    today = date.today().isoformat()
    last = run.get("last_run_date") or (date.today() - timedelta(days=1)).isoformat()
    queue = [load(f, {}) for f in sorted((STATE / "confirm-queue").glob("*.json"))]
    sweep_due, since = sweep_state(run)
    waiting = parse(run.get("board_write_waiting_since"))
    if waiting and time.time() - waiting.timestamp() > BOARD_WAIT_SECONDS:
        waiting = None
    print(json.dumps({
        "today": today,
        "first_run_today": run.get("last_run_date") != today,
        "notes_after": last.replace("-", "/"),
        "unsynced_queue_items": [q.get("id") for q in queue if q.get("boardSync") == "pending"],
        "brief_written_today": run.get("brief_date") == today,
        "sweep_due": sweep_due,
        "sweep_since": since.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "sweep_since_unix": int(since.timestamp()),
        "mail_sweep_after": since.astimezone().strftime("%Y/%m/%d"),
        "board_write_waiting_since": waiting.isoformat(timespec="seconds") if waiting else None,
        # The weekly review is due on the first run of a week that has none yet.
        "review_due": bool(CFG.get("weekly_review", True)) and run.get("review_week") != iso_week(),
    }, indent=1))


def keep_lock():
    """A long run keeps its lock: refresh its modification time while it works."""
    try:
        os.utime(LOCK)
    except OSError:
        pass


def seen(ids):
    keep_lock()
    processed = load(STATE / "processed.json", {})
    for source_id in ids:
        if source_id not in processed:
            print(source_id)


def filed(source_id, note_file):
    keep_lock()
    STATE.mkdir(parents=True, exist_ok=True)
    processed = load(STATE / "processed.json", {})
    processed[source_id] = {"file": note_file, "filedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (STATE / "processed.json").write_text(json.dumps(processed, indent=1) + "\n")
    print("recorded " + source_id)


def finish(brief_written, swept=False, review=False):
    STATE.mkdir(parents=True, exist_ok=True)
    run = load(RUN, {})
    began = None
    try:
        began = parse(LOCK.read_text().strip())
    except OSError:
        pass
    seconds = round((datetime.now(timezone.utc) - began).total_seconds()) if began else None
    with (STATE / "run-log.jsonl").open("a") as log:
        log.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "seconds": seconds,
                              "brief": bool(brief_written), "sweep": bool(swept), "review": bool(review)}) + "\n")
    if review:
        run["review_week"] = iso_week()
    today = date.today().isoformat()
    run.update(last_run_date=today, last_run_at=datetime.now(timezone.utc).isoformat())
    if brief_written:
        run["brief_date"] = today
    if swept:
        run["last_sweep_at"] = datetime.now(timezone.utc).isoformat()
    RUN.write_text(json.dumps(run, indent=1) + "\n")
    LOCK.unlink(missing_ok=True)
    print("finished")


def board(waiting):
    keep_lock()
    STATE.mkdir(parents=True, exist_ok=True)
    run = load(RUN, {})
    if waiting:
        run["board_write_waiting_since"] = datetime.now(timezone.utc).isoformat()
    else:
        run.pop("board_write_waiting_since", None)
    RUN.write_text(json.dumps(run, indent=1) + "\n")
    print("board write waiting" if waiting else "board write done")


if __name__ == "__main__":
    args = [a for i, a in enumerate(sys.argv[1:]) if a != "--config" and (i == 0 or sys.argv[i] != "--config")]
    cmd = args[0] if args else ""
    if cmd == "start":
        start()
    elif cmd == "seen":
        seen(args[1:])
    elif cmd == "filed" and len(args) >= 3:
        filed(args[1], args[2])
    elif cmd == "finish":
        finish("--brief" in args, "--sweep" in args, "--review" in args)
    elif cmd in ("board-wait", "board-done"):
        board(cmd == "board-wait")
    else:
        print(__doc__)
        sys.exit(1)
