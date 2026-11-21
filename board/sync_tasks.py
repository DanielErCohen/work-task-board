#!/usr/bin/env python3
"""Sync tasks.md with the task board page's database.

tasks.md stays the source of truth. The board is a view you can edit; its edits
come back into tasks.md through `import`.

  python3 sync_tasks.py check             # every row of tasks.md is well formed (10 cells, dates in the date cells)
  python3 sync_tasks.py export            # tasks.md -> <out>/<ID>.json, one file per task, ready to write to the board
  python3 sync_tasks.py import <dir>      # board edits (JSON files saved from a board query) -> tasks.md
  python3 sync_tasks.py stale             # open tasks whose summary file is missing or older than their notes
  python3 sync_tasks.py stamp T004 T007   # after writing those summaries: record that they match the notes
  python3 sync_tasks.py plan <dir>        # after export: which tasks differ from the board copy saved in <dir>

Where the files are comes from a config file, board.config.json. It is looked for in this order:
--config <path>, the BOARD_CONFIG environment variable, the current folder, then the folder of this
script and its parents. Paths inside it are relative to the folder that holds it. Every path can
also be given on the command line: --tasks, --summaries, --out.

  {
    "tasks": "tasks.md",                 the task table
    "summaries": "summaries",            one <ID>.json per task
    "out": "board/out/docs",             where export writes
    "state": "state",                    cards, brief and run state (used by the job scripts)
    "link_roots": ["meetings"],          folders searched for [[note-name]] links in task notes (optional;
                                         a folder outside this one is written as "../meetings")
    "link_base": "",                     web address of THIS folder, ending in "/", that turns a file path
                                         into a link (optional; empty means no links)
    "statuses": [...], "open_statuses": [...], "new_status": "..."
                                         only when they differ from the defaults below. The closed statuses
                                         come last: first the one that means done, then the one that means dropped.
    "sweeps": true, "weekly_review": true, "sweep_hours": [8, 14]     read by job/scripts/hourly_precheck.py
  }

A board edit is a document with `dirty: true` and `editedFields`, the list of fields the page changed.
Import applies only those fields of only those documents, so text written to tasks.md in the meantime
(a note the hourly job added) is kept. Lines that are not task rows keep their place in the file.
"""
import hashlib, json, os, re, sys
from datetime import date
from pathlib import Path

COLS = ["id", "title", "status", "priority", "category", "due", "notes", "opened", "lastChanged", "closed"]
EDITABLE = ["title", "status", "priority", "category", "due", "notes", "closed"]
STATUSES = ["In Review", "In Progress", "Postponed", "Pending others", "Planning", "Not started", "Done", "Abandoned"]
OPEN_STATUSES = STATUSES[:-2]
PRIORITIES = ["Critical", "High", "Medium", "Low"]
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# The owner's role on a task and its point of contact live at the very start of the notes cell, in this order:
# "RACI: A, I. POC: Full Name." The board shows them as its RACI and POC columns and edits them as fields.
OWNER_RE = re.compile(r"^(?:RACI: ([RACI](?:, ?[RACI])*)\.\s*)?(?:POC: ([^.;|]+)\.\s*)?")
ROW_RE = re.compile(r"^\|\s*T\d+\s*\|")   # a task row; check, export and import all use this one pattern


def split_cells(line):
    """The cells of a table line. The outer pipes are cut off one at a time, so an empty last cell survives."""
    t = line.strip()
    if t.startswith("|"):
        t = t[1:]
    if t.endswith("|"):
        t = t[:-1]
    return [c.strip() for c in t.split("|")]

CFG = {}          # filled by configure()
ROOT = Path(".")  # the folder that holds board.config.json
TASKS = SUMMARIES = OUT = None


def find_config(explicit):
    if explicit:
        return Path(explicit)
    if os.environ.get("BOARD_CONFIG"):
        return Path(os.environ["BOARD_CONFIG"])
    here = Path(__file__).resolve().parent
    for folder in [Path.cwd(), here, *here.parents]:
        if (folder / "board.config.json").exists():
            return folder / "board.config.json"
    return None


def configure(argv):
    """Read the options, load the config and set the paths. Returns the remaining arguments."""
    global CFG, ROOT, TASKS, SUMMARIES, OUT, STATUSES, OPEN_STATUSES
    opts, rest, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        if a in ("--config", "--tasks", "--summaries", "--out") and i + 1 < len(argv):
            opts[a[2:]] = argv[i + 1]
            i += 2
        else:
            rest.append(a)
            i += 1
    # --tasks without --config is the config-less mode: no other board's config is picked up by accident.
    cfg_path = find_config(opts.get("config")) if ("config" in opts or "tasks" not in opts) else None
    if cfg_path:
        if not cfg_path.exists():
            sys.exit(f"config file not found: {cfg_path}")
        try:
            CFG = json.loads(cfg_path.read_text())
        except ValueError:
            print(f"{cfg_path}: not valid JSON", file=sys.stderr)
            sys.exit(2)
        ROOT = cfg_path.resolve().parent
    elif "tasks" in opts:
        ROOT = Path(opts["tasks"]).resolve().parent
    else:
        sys.exit("No board.config.json found. Run from the folder that holds it, or pass --config <path> or --tasks <path to tasks.md>.")
    pick = lambda key, default: Path(opts[key]).resolve() if key in opts else (ROOT / CFG.get(key, default))
    TASKS = pick("tasks", "tasks.md")
    SUMMARIES = pick("summaries", "summaries")
    OUT = pick("out", "board/out/docs")
    if CFG.get("statuses"):
        STATUSES = list(CFG["statuses"])
        for s in CFG.get("open_statuses", []):
            if s not in STATUSES:
                sys.exit(f"{cfg_path}: open_statuses entry '{s}' is not in statuses")
        OPEN_STATUSES = [s for s in CFG.get("open_statuses", STATUSES[:-2]) if s in STATUSES]
    if CFG.get("new_status") and CFG["new_status"] not in OPEN_STATUSES:
        sys.exit(f"{cfg_path}: new_status '{CFG['new_status']}' is not an open status")
    if not TASKS.exists():
        sys.exit(f"task table not found: {TASKS}")
    return rest


def closed_statuses():
    return [s for s in STATUSES if s not in OPEN_STATUSES]


def new_status():
    """The status a task gets when none is given."""
    if CFG.get("new_status") in OPEN_STATUSES:
        return CFG["new_status"]
    return "Not started" if "Not started" in OPEN_STATUSES else OPEN_STATUSES[0]


def notes_hash(notes):
    return hashlib.sha1(notes.encode()).hexdigest()[:12]


def load_summary(tid):
    p = SUMMARIES / f"{tid}.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except ValueError:
        return {}


def save_summary(tid, s):
    SUMMARIES.mkdir(parents=True, exist_ok=True)
    (SUMMARIES / f"{tid}.json").write_text(json.dumps(s, ensure_ascii=False, indent=1) + "\n")


def split_owner(notes):
    """Return (raci, poc, notes without the two leading markers)."""
    m = OWNER_RE.match(notes)
    return (m.group(1) or "").replace(" ", "").replace(",", ", "), (m.group(2) or "").strip(), notes[m.end():]


def owner_prefix(raci, poc):
    letters = [c for c in "RACI" if c in str(raci or "").upper()]
    poc = re.sub(r"\s+", " ", re.sub(r"[.;|]", " ", str(poc or ""))).strip()
    return ("RACI: " + ", ".join(letters) + ". " if letters else "") + ("POC: " + poc + ". " if poc else "")


def read_rows():
    """Return (lines, rows). `lines` is the whole file; a row is a dict plus 'line' (its index in lines)."""
    lines = TASKS.read_text().split("\n")
    rows = []
    for i, line in enumerate(lines):
        if ROW_RE.match(line) and line.rstrip().endswith("|"):
            cells = split_cells(line)
            if len(cells) == len(COLS):
                row = dict(zip(COLS, cells))
                row["line"] = i
                rows.append(row)
    return lines, rows


def index_files():
    """Map note names ([[name]]) to paths relative to the config folder."""
    idx = {}
    for sub in CFG.get("link_roots", []):
        base = ROOT / sub
        if not base.is_dir():
            continue
        for p in base.rglob("*.md"):
            key = p.parent.name if p.name == "README.md" else p.stem
            idx.setdefault(key, Path(os.path.relpath(p, ROOT)).as_posix())
    return idx


def refs_for(notes, idx):
    base = CFG.get("link_base", "")
    link = lambda path: base + path if base and path else ""
    refs, seen = [], set()

    def add(kind, label, url):
        if (kind, label) in seen:
            return
        seen.add((kind, label))
        refs.append({"kind": kind, "label": label, "url": url})

    for slug in re.findall(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]", notes):
        path = idx.get(slug)
        kind = "meeting" if re.match(r"\d{4}-\d{2}-\d{2}[_-]", slug) else (
            "person" if path and "/people/" in path else "note")
        add(kind, slug, link(path))
    kind_of = lambda u: "artifact" if "claude.ai" in u else "doc" if "docs.google.com" in u else "link"
    for label, url in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", notes):
        add(kind_of(url), label, url)
    for url in re.findall(r"(?<!\()https?://[^\s)|]+", notes):
        add(kind_of(url), url, url)
    for path in re.findall(r"`([\w./-]+\.(?:md|html|json|csv|py|xlsx))`", notes):
        add("file", path, link(path) if (ROOT / path).exists() else "")
    for tid in re.findall(r"\bT\d{3}\b", notes):
        add("task", tid, "")
    return refs


def is_day(v):
    if not DAY_RE.match(v):
        return False
    try:
        date.fromisoformat(v)
    except ValueError:
        return False
    return True


def stray_table_lines(lines):
    """(line number, first cell) of every line of the task table that is not a task row, a header or a separator.
    The task table is the unbroken block of lines starting with a pipe that holds the ID header or a task row."""
    out, i = [], 0
    while i < len(lines):
        if not lines[i].startswith("|"):
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].startswith("|"):
            j += 1
        if any(ROW_RE.match(l) or split_cells(l)[0] == "ID" for l in lines[i:j]):
            for n in range(i, j):
                first = split_cells(lines[n])[0]
                if not (ROW_RE.match(lines[n]) or first == "ID" or re.match(r"^\|[\s:|-]+$", lines[n].strip())):
                    out.append((n + 1, first))
        i = j
    return out


def check():
    """Return the list of problems in tasks.md; an empty list means every row is well formed.

    Every writer runs this after editing tasks.md. export and import refuse to run while it reports
    anything, so a malformed row (a note written into the due cell, a pipe inside a cell) never
    reaches the board."""
    problems, seen = [], set()
    all_lines = TASKS.read_text().split("\n")
    for n, first in stray_table_lines(all_lines):
        problems.append(f"line {n}: '{first[:40]}' is not a task ID (T and digits), so this line of the table is ignored")
    for n, line in enumerate(all_lines, 1):
        if not ROW_RE.match(line):
            continue
        cells = split_cells(line)
        tid = cells[0]
        if not line.rstrip().endswith("|"):
            problems.append(f"line {n} {tid}: the row does not end with a pipe (a line break inside a cell?)")
            continue
        if len(cells) != len(COLS):
            problems.append(f"line {n} {tid}: {len(cells)} cells, expected {len(COLS)} (a pipe inside a cell, or a missing cell)")
            continue
        r = dict(zip(COLS, cells))
        if tid in seen:
            problems.append(f"line {n} {tid}: this id appears twice")
        seen.add(tid)
        if not r["title"]:
            problems.append(f"line {n} {tid}: empty title")
        if r["status"] not in STATUSES:
            problems.append(f"line {n} {tid}: status '{r['status'][:40]}' is not one of {', '.join(STATUSES)}")
        if r["priority"] not in PRIORITIES:
            problems.append(f"line {n} {tid}: priority '{r['priority'][:40]}' is not one of {', '.join(PRIORITIES)}")
        if not r["category"] or len(r["category"]) > 40:
            problems.append(f"line {n} {tid}: category '{r['category'][:40]}' is empty or longer than 40 characters")
        for k in ("due", "closed"):
            if r[k] and not is_day(r[k]):
                problems.append(f"line {n} {tid}: {k} is '{r[k][:40]}', expected YYYY-MM-DD or empty (notes belong in the notes cell, the 7th)")
        for k in ("opened", "lastChanged"):
            if not is_day(r[k]):
                problems.append(f"line {n} {tid}: {k} is '{r[k][:40]}', expected YYYY-MM-DD")
    return problems


def check_or_exit(doing):
    problems = check()
    if problems:
        print(f"tasks.md has malformed rows; {doing}. Fix them and run again:")
        for x in problems:
            print("  " + x)
        sys.exit(2)


def export():
    check_or_exit("nothing was exported")
    _, rows = read_rows()
    idx = index_files()
    if OUT.resolve() == ROOT.resolve() or (OUT / "board.config.json").exists():
        sys.exit(f"export refused: {OUT} is the board folder or holds board.config.json")
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("T*.json"):
        if re.fullmatch(r"T\d+\.json", f.name):
            f.unlink()
    for r in rows:
        doc = {k: r[k] for k in COLS}
        doc["raci"], doc["poc"], doc["notes"] = split_owner(doc["notes"])
        doc["notes"] = doc["notes"].replace(" /  / ", "\n\n")
        doc["refs"] = refs_for(r["notes"], idx)
        s = load_summary(r["id"])
        dec = dict(s.get("decision") or {})
        if str(dec.get("url", "")).startswith("meeting:"):
            slug = dec["url"][8:]
            path = idx.get(slug) or next((v for k, v in idx.items() if k.startswith(slug)), "")
            dec["url"] = CFG.get("link_base", "") + path if path and CFG.get("link_base") else ""
        doc["description"] = s.get("description", "")
        doc["decision"] = dec if dec.get("text") else None
        doc["details"] = s.get("details", [])
        doc["summaryStale"] = bool(s) and s.get("notesHash") != notes_hash(r["notes"])
        doc["dirty"] = False
        doc["editedFields"] = []
        doc["syncedAt"] = date.today().isoformat()
        (OUT / f"{r['id']}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    print(f"exported {len(rows)} tasks to {OUT}")


def cell(v):
    return str(v or "").replace("|", "/").replace("\n", " / ").strip()


def row_text(r):
    text = "| " + " | ".join(cell(r[k]) for k in COLS) + " |"
    while "|  |" in text:
        text = text.replace("|  |", "| |")
    return text


def import_(src):
    check_or_exit("nothing was imported")  # a malformed row would not be recognised below
    lines, rows = read_rows()
    by_id = {r["id"]: r for r in rows}
    edits = []
    for f in sorted(Path(src).rglob("*.json")):
        try:
            d = json.loads(f.read_text())
        except ValueError:
            print(f"skipped {f.name}: not valid JSON")
            continue
        d = d.get("data", d) if isinstance(d, dict) else None
        if not isinstance(d, dict):
            print(f"skipped {f.name}: not a task document")
            continue
        if d.get("dirty"):
            edits.append(d)
    today = date.today().isoformat()
    closed = closed_statuses()
    changed, new_rows, clear, rejected = [], [], [], []
    next_n = max([int(r["id"][1:]) for r in rows] or [0]) + 1
    for d in edits:
        tid = d.get("id")
        if not re.fullmatch(r"T[0-9]+", str(tid or "")):
            print(f"skipped a document without a task id: {str(tid)[:40]}")
            continue
        clear.append(tid)
        r = by_id.get(tid)
        if r is not None and d.get("isNew") and cell(d.get("title")) != r["title"]:
            # A task created on the page took an id that a row written here in the meantime already has.
            fresh = "T" + str(next_n).zfill(3)
            print(f"{tid} was created on the page, but tasks.md already has another {tid}; the page's task is imported as {fresh}. "
                  f"Push both {tid} and {fresh} to the board.")
            tid, r = fresh, None
            clear.append(fresh)
        is_new = r is None
        if is_new:
            r = {k: "" for k in COLS}
            opened = str(d.get("opened") or "")
            r.update(id=tid, opened=opened if is_day(opened) else today)
            next_n = max(next_n, int(tid[1:]) + 1)
            by_id[tid] = r
            new_rows.append(r)
        # The page lists what it changed in editedFields. A document without the list (a new task, or one
        # written by another tool) is applied whole.
        only = d.get("editedFields") if isinstance(d.get("editedFields"), list) and not is_new else None
        wants = lambda k: k in d and (only is None or k in only)
        before = {k: r[k] for k in EDITABLE}
        raci, poc, _ = split_owner(r["notes"])
        for k in EDITABLE:
            if not wants(k):
                continue
            v = cell(d[k])
            if k in ("due", "closed") and v and not is_day(v):
                print(f"not applied: {tid} {k} '{v[:40]}' is not a date; kept '{r[k]}'")
                rejected.append(tid)
                continue
            if k == "status" and v not in STATUSES:
                if v:
                    print(f"not applied: {tid} status '{v[:40]}' is not a known status; kept '{r[k]}'")
                    rejected.append(tid)
                continue
            if k == "priority" and v not in PRIORITIES:
                if v:
                    print(f"not applied: {tid} priority '{v[:40]}' is not a known priority; kept '{r[k]}'")
                    rejected.append(tid)
                continue
            if k == "category" and len(v) > 40:
                print(f"not applied: {tid} category '{v[:40]}' is longer than 40 characters; kept '{r[k]}'")
                rejected.append(tid)
                continue
            if k == "notes":   # the board's notes field never holds the owner markers; they are put back below
                v = split_owner(v)[2]
            r[k] = v
        body = split_owner(r["notes"])[2]
        r["notes"] = owner_prefix(d["raci"] if wants("raci") else raci, d["poc"] if wants("poc") else poc) + body
        if wants("description"):  # the description is edited on the board and kept in the task's summary file
            s = load_summary(tid)
            if str(d["description"] or "").strip() != s.get("description", ""):
                s.setdefault("id", tid)
                s["description"] = str(d["description"] or "").strip()
                save_summary(tid, s)
                print(f"description updated: {tid}")
        r["status"] = r["status"] or new_status()
        r["priority"] = r["priority"] or "Medium"
        r["category"] = r["category"] or "general"
        if r["status"] in closed and not r["closed"]:
            r["closed"] = today
        if r["status"] not in closed and r["closed"] and (wants("status") or is_new):
            r["closed"] = ""   # reopened
        if {k: r[k] for k in EDITABLE} != before or is_new:
            r["lastChanged"] = today
            changed.append(tid)
            if not is_new:
                lines[r["line"]] = row_text(r)
    if new_rows:   # new tasks go right after the last row of the table
        at = max((r["line"] for r in rows), default=None)
        if at is None:
            at = max((i for i, line in enumerate(lines) if line.startswith("|")), default=len(lines) - 1)
        lines[at + 1:at + 1] = [row_text(r) for r in sorted(new_rows, key=lambda r: int(r["id"][1:]))]
    if changed:
        TASKS.write_text("\n".join(lines))
    print("updated: " + (", ".join(changed) if changed else "none"))
    if rejected:
        print("edits not applied (the next push overwrites them on the board; tell the owner): " + ", ".join(sorted(set(rejected))))
    print("clear dirty on (push each of these to the board): " + (", ".join(clear) or "none"))


def stale():
    """Open tasks whose summary is missing or was written from older notes."""
    check_or_exit("stale was not run")
    _, rows = read_rows()
    out = []
    for r in rows:
        if r["status"] not in OPEN_STATUSES:
            continue
        s = load_summary(r["id"])
        if not s.get("description") or not (s.get("decision") or {}).get("text"):
            out.append(r["id"] + " (missing)")
        elif s.get("notesHash") != notes_hash(r["notes"]):
            out.append(r["id"] + " (notes changed)")
    print("summaries to write or refresh: " + (", ".join(out) or "none"))


def stamp(ids):
    """Record that these tasks' summaries match their current notes."""
    check_or_exit("nothing was stamped")
    _, rows = read_rows()
    by_id = {r["id"]: r for r in rows}
    done = []
    for tid in ids:
        s = load_summary(tid)
        if tid not in by_id or not s:
            print(f"skipped {tid}: no such task or no summary file")
            continue
        s["notesHash"] = notes_hash(by_id[tid]["notes"])
        save_summary(tid, s)
        done.append(tid)
    print("stamped: " + (", ".join(done) or "none"))


def plan(src):
    board = {}
    for f in Path(src).rglob("*.json"):
        try:
            d = json.loads(f.read_text())
        except ValueError:
            print(f"skipped {f.name}: not valid JSON")
            continue
        d = d.get("data", d) if isinstance(d, dict) else None
        if isinstance(d, dict):
            board[d.get("id", f.stem)] = d
    skip = {"syncedAt", "dirty", "editedFields"}
    defaults = {"raci": "", "poc": "", "description": "", "decision": None, "details": [], "summaryStale": False}
    new, changed = [], []
    for f in sorted(OUT.glob("*.json")):
        d = json.loads(f.read_text())
        b = board.get(d["id"])
        if b is None:
            new.append(d["id"])
            continue
        mine = {k: v for k, v in d.items() if k not in skip}
        theirs = {k: b.get(k, defaults.get(k)) for k in mine}
        if mine != theirs:
            changed.append(d["id"])
    gone = sorted(set(board) - {f.stem for f in OUT.glob("*.json")})
    print("new: " + (", ".join(new) or "none"))
    print("changed: " + (", ".join(changed) or "none"))
    print("on board only: " + (", ".join(gone) or "none"))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) >= 2 else 1)
    args = configure(sys.argv[1:])
    cmd = args[0] if args else ""
    if cmd == "export":
        export()
    elif cmd == "stale":
        stale()
    elif cmd == "stamp" and len(args) >= 2:
        stamp(args[1:])
    elif cmd == "check":
        check_or_exit("fix them before any export or import")
        print("tasks.md: every row is well formed")
    elif cmd == "plan" and len(args) >= 2:
        plan(args[1])
    elif cmd == "import" and len(args) >= 2:
        import_(args[1])
    else:
        print(__doc__)
        sys.exit(1)
