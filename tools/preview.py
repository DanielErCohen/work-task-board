#!/usr/bin/env python3
"""Show the board page on this computer, without publishing anything.

  python3 tools/preview.py                      in the kit: the sample, with its dates moved to today
                                                in your board folder: your own tasks
  python3 tools/preview.py --data <folder>      a board folder (the one that holds board.config.json)
  python3 tools/preview.py --port 8765          another port (default 8765)
  python3 tools/preview.py --no-serve --out <folder>   only write index.html there
  python3 tools/preview.py --no-serve --out <folder> --about <link>   the same, with a "Set up your own" link in the notice

Then open http://localhost:8765/ . Add ?theme=dark or ?theme=light to force a theme, and ?ask=off to see
the page without the Ask Claude button.

The published page talks to Claude's artifact runtime (a shared database, the viewer's identity, Ask
Claude). Here a small stand-in takes its place: the data is read once from the folder, edits live in the
browser tab only and are gone on reload, and Ask Claude answers with a fixed line. Nothing leaves this
computer and nothing is written to your files.

--no-serve --out with the sample writes a static demo that can sit on any web host. It keeps the sample's own
dates and carries the day they were written for; when a visitor opens the page, the stand-in moves every
date by the distance from that day to the visitor's today, so the page never ages. A line at the top says
the data is made up and that edits stay in the tab. The demo opens in light mode; ?theme=dark switches it. With --data the dates are left as they are.
"""
import http.server, json, shutil, subprocess, sys, tempfile
from functools import partial
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
# KIT is the folder above tools/: the kit itself, or a board folder that holds a copy of this script.

STUB = r"""
<script>
/* Local stand-in for the artifact runtime: an in-memory database with live listeners. Preview only. */
(() => {
  const builtFor = __BUILT_FOR__;   // static demo only: the day the sample's dates were written for
  let seed = __SEED__;
  const q = new URLSearchParams(location.search);
  if (builtFor) {   // move every date in the data by (the visitor's today minus that day), so the sample day is always today
    const utc = (y, m, d) => Date.UTC(+y, +m - 1, +d), t = new Date();
    const delta = Math.round((utc(t.getFullYear(), t.getMonth() + 1, t.getDate()) - utc(...builtFor.split("-"))) / 864e5);
    const move = (m, y, mo, d) => {
      const at = new Date(utc(y, mo, d));
      return at.getUTCDate() === +d ? new Date(+at + delta * 864e5).toISOString().slice(0, 10) : m;   // leave a non-date alone
    };
    if (delta) seed = JSON.parse(JSON.stringify(seed).replace(/(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)/g, move));
  }
  const theme = q.get("theme") || (builtFor ? "light" : "");   // the static demo opens in light; ?theme=dark switches it
  if (theme) { document.documentElement.dataset.theme = theme; document.documentElement.style.colorScheme = theme; }
  const store = {}, subs = {};
  for (const [name, docs] of Object.entries(seed)) store[name] = new Map(Object.entries(docs));
  const coll = (name) => (store[name] = store[name] || new Map());
  const fire = (name) => (subs[name] || []).forEach((cb) => cb({ docs: [...coll(name).entries()].map(([id, d]) => ({ id, exists: true, data: () => ({ ...d }) })) }));
  const later = (name) => new Promise((ok) => setTimeout(() => { fire(name); ok(); }, 0));
  const db = {
    collection: (name) => ({ onSnapshot: (cb) => { (subs[name] = subs[name] || []).push(cb); setTimeout(() => fire(name), 0); return () => {}; } }),
    doc: (path) => {
      const [name, id] = path.split("/");
      return {
        set: (d) => { coll(name).set(id, { ...d }); return later(name); },
        update: (d) => { coll(name).set(id, { ...(coll(name).get(id) || {}), ...d }); return later(name); },
        delete: () => { coll(name).delete(id); return later(name); },
      };
    },
  };
  const sample = Object.assign(async (messages, opts) => {
    const text = builtFor ? "This is a made-up demo: Ask Claude answers on your own published board." : "This is the local preview: Ask Claude answers only on the published page.";
    if (opts && opts.onText) opts.onText({ text });
    return { text };
  }, { limits: async () => ({ tools: true }) });
  if (builtFor) {   // static demo: the welcome says it is the sample's, and the Setup panel says nothing is applied here
    const swap = [["Saved. Claude applies it within the hour.", "Saved in this tab only. On your own board, Claude applies it within the hour."],
                  ["Saved. Claude applies it the next time you talk to it in your board folder.", "Saved in this tab only. On your own board, Claude applies it the next time you talk to it."],
                  ["In the Claude app, open the Code tab,", "On your own board: in the Claude app, open the Code tab,"]];
    new MutationObserver(() => {
      const wt = document.getElementById("wTitle");
      if (wt && !document.getElementById("demoWelcome")) wt.insertAdjacentHTML("afterend", '<p id="demoWelcome" style="margin:6px 0 0;font-size:13.5px;color:var(--text-muted)">The sample\'s welcome: Megan and everything on this board are invented.</p>');
      for (const el of document.querySelectorAll("#drawer .sline")) for (const [a, b] of swap) if (el.innerHTML.startsWith(a)) el.innerHTML = b + el.innerHTML.slice(a.length);
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
  window.claude = { use: async (name) => name === "db" ? db : name === "user" ? { can: async () => true } : name === "sample" && q.get("ask") !== "off" ? sample : null };
})();
</script>
"""


BANNER = """<div style="padding:8px 16px;text-align:center;font:13px/1.4 var(--font, system-ui, sans-serif);background:var(--primary-light, #E7ECFF);color:var(--text, #1b1f2a);border-bottom:1px solid var(--border, #d0d5e2)">This is a made-up sample board. Every person and figure is invented. Your edits stay in this browser tab, and Ask Claude answers with a fixed line here.__ABOUT__</div>
"""


def build(data, owner="", built_for=None, about="", setup=None):
    """Return the preview page for the board folder `data`. `owner` replaces the name in the page's config block.
    `built_for` (an ISO day) makes a static demo: the page moves the data's dates to the visitor's today and shows a sample notice.
    `setup` is the setup document to show; by default the folder's own state/setup.json, when it has one."""
    cfg_path = data / "board.config.json"
    if not cfg_path.exists():
        sys.exit(f"{data} holds no board.config.json")
    cfg = json.loads(cfg_path.read_text())
    out = Path(tempfile.mkdtemp(prefix="board-preview-"))
    subprocess.run([sys.executable, str(KIT / "board" / "sync_tasks.py"), "--config", str(cfg_path), "--out", str(out), "export"], check=True, stdout=subprocess.DEVNULL)
    read = lambda p: json.loads(p.read_text())
    state = data / cfg.get("state", "state")
    setup = setup or state / "setup.json"
    seed = {"tasks": {p.stem: read(p) for p in sorted(out.glob("*.json"))},
            "confirm": {c["id"]: c for c in (read(p) for p in sorted((state / "confirm-queue").glob("*.json")))},
            "brief": {"today": read(state / "brief-today.json")} if (state / "brief-today.json").exists() else {},
            "prep": {},
            "setup": {"state": read(setup)} if setup and setup.exists() else {}}
    shutil.rmtree(out, ignore_errors=True)   # the export folder is only needed to build the seed
    page = (KIT / "board" / "tasks-board.html").read_text()
    local = data / "board" / "tasks-board.html"   # a set-up folder has its own copy with its own config block
    if local.exists():
        page = local.read_text()
    if owner:   # the sample belongs to an invented person; show her name where the page's config has a placeholder
        page = page.replace("</script>", "</script>\n<script>window.BOARD_CONFIG.owner = " + json.dumps(owner) + ";</script>", 1)
    stub = STUB.replace("__BUILT_FOR__", json.dumps(built_for)).replace("__SEED__", json.dumps(seed, ensure_ascii=False).replace("</", "<\\/"))
    more = ' <a href="' + about.replace('"', '%22') + '" style="color:inherit;font-weight:600">Set up your own</a>' if about else ""
    return '<!doctype html>\n<html lang="en">\n<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n</head>\n<body>\n' + stub + (BANNER.replace("__ABOUT__", more) if built_for else "") + page + "\n</body>\n</html>\n"


if __name__ == "__main__":
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(__doc__)
        sys.exit(0)
    opt = lambda name, default=None: args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default
    owner, built_for, made, setup = "", None, [], None   # `made`: temporary folders to remove once the page is written
    static = "--no-serve" in args
    if opt("--data"):
        data = Path(opt("--data")).resolve()
    elif (KIT / "sample").is_dir():
        sys.path.insert(0, str(KIT / "tools"))
        from load_sample import copy_sample
        data = Path(tempfile.mkdtemp(prefix="board-sample-"))
        made.append(data)
        if static:   # a static demo keeps the sample's own dates; the page moves them to each visitor's today
            copy_sample(data, shift=False)
            built_for = json.loads((data / "state" / "brief-today.json").read_text())["date"]
        else:
            copy_sample(data)
        owner = "Megan Clark"   # the invented owner of the sample
        setup = KIT / "sample" / "state" / "setup.json"   # load_sample.py never copies it into a board folder
    elif (KIT / "board.config.json").exists():
        data = KIT
    else:
        sys.exit("No sample folder and no board.config.json here. Pass --data <board folder>.")
    site_is_temp = not opt("--out")
    site = Path(opt("--out") or tempfile.mkdtemp(prefix="board-site-")).resolve()
    site.mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text(build(data, owner, built_for, opt("--about", ""), setup))
    for d in made:
        shutil.rmtree(d, ignore_errors=True)
    if static:
        print(f"wrote {site / 'index.html'}")
        sys.exit(0)
    port = int(opt("--port", "8765"))
    print(f"Board preview: http://localhost:{port}/   (Ctrl+C to stop)")
    try:
        http.server.ThreadingHTTPServer(("127.0.0.1", port), partial(http.server.SimpleHTTPRequestHandler, directory=str(site))).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if site_is_temp:
            shutil.rmtree(site, ignore_errors=True)
