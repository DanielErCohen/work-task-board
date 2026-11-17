#!/usr/bin/env python3
"""Numbers for the weekly review of the To confirm queue and the hourly job.

  efficiency_report.py [days]     print JSON for the last <days> days (default 7)

Reads confirm-queue/*.json and run-log.jsonl from the state folder named in board.config.json (found the
same way as in hourly_precheck.py). It measures outcomes and run time; token use is not recorded locally.
"""
import json, os, statistics, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def state_dir():
    args = sys.argv[1:]
    explicit = args[args.index("--config") + 1] if "--config" in args and args.index("--config") + 1 < len(args) else os.environ.get("BOARD_CONFIG")
    here = Path(__file__).resolve().parent
    path = Path(explicit) if explicit else next((f / "board.config.json" for f in [Path.cwd(), here, *here.parents] if (f / "board.config.json").exists()), None)
    if not path or not path.exists():
        sys.exit("No board.config.json found. Run from the folder that holds it, or pass --config <path>.")
    return path.resolve().parent / json.loads(path.read_text()).get("state", "state")


def parse(ts):
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def main(days):
    state = state_dir()
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    items = []
    for f in sorted((state / "confirm-queue").glob("*.json")):
        try:
            items.append(json.loads(f.read_text()))
        except (OSError, ValueError):
            pass
    recent = [i for i in items if (parse(i.get("createdAt")) or now) >= since]
    answered = [i for i in recent if i.get("answer")]
    prepared = [i for i in recent if i.get("prepared") or i.get("options") or i.get("visual")]

    def matched(i):
        opts = i.get("options") or []
        rec = next((o.get("key") for o in opts if o.get("recommended")), None)
        if i.get("answer") != "confirm":
            return False
        return rec is None or not i.get("choice") or i.get("choice") == rec

    hours = [(parse(i.get("answeredAt")) - parse(i.get("createdAt"))).total_seconds() / 3600
             for i in answered if parse(i.get("answeredAt")) and parse(i.get("createdAt"))]
    runs = []
    try:
        for line in (state / "run-log.jsonl").read_text().splitlines():
            r = json.loads(line)
            if (parse(r.get("at")) or now) >= since:
                runs.append(r)
    except (OSError, ValueError):
        pass
    secs = [r["seconds"] for r in runs if isinstance(r.get("seconds"), (int, float))]
    by = lambda key: {k: sum(1 for i in recent if (i.get(key) or "none") == k) for k in sorted({(i.get(key) or "none") for i in recent})}
    print(json.dumps({
        "window_days": days,
        "items_created": len(recent),
        "by_origin": by("origin"),
        "by_lane": by("lane"),
        "answered": len(answered),
        "confirmed": sum(1 for i in answered if i.get("answer") == "confirm"),
        "changed": sum(1 for i in answered if i.get("answer") == "change"),
        "dropped": sum(1 for i in answered if i.get("answer") == "drop"),
        "answer_matched_recommendation": sum(1 for i in answered if matched(i)),
        "answered_with_a_comment": sum(1 for i in answered if (i.get("comment") or "").strip()),
        "prepared_items": len(prepared),
        "prepared_answered_without_comment": sum(1 for i in prepared if i.get("answer") and not (i.get("comment") or "").strip()),
        "still_open": sum(1 for i in recent if i.get("state") == "open"),
        "open_older_than_3_days": [i.get("title") for i in items if i.get("state") == "open" and (parse(i.get("createdAt")) or now) < now - timedelta(days=3)],
        "median_hours_to_answer": round(statistics.median(hours), 1) if hours else None,
        "runs": len(runs),
        "runs_with_work_over_60s": sum(1 for x in secs if x > 60),
        "run_seconds_total": sum(secs),
        "run_seconds_median": statistics.median(secs) if secs else None,
        "run_seconds_max": max(secs) if secs else None,
    }, indent=1))


if __name__ == "__main__":
    nums = [a for a in sys.argv[1:] if a.isdigit()]
    main(int(nums[0]) if nums else 7)
