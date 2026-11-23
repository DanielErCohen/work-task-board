"""Tests for the Work Task Board kit. Standard library only.

Run from the repo root:  python -m unittest discover -s tests -v

Every test works in a fresh temporary folder and never writes inside the repo.
"""
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import unquote

REPO = Path(__file__).resolve().parent.parent
SYNC = REPO / "board" / "sync_tasks.py"
PRECHECK = REPO / "job" / "scripts" / "hourly_precheck.py"
EFFICIENCY = REPO / "job" / "scripts" / "efficiency_report.py"
LOAD_SAMPLE = REPO / "tools" / "load_sample.py"
PREVIEW = REPO / "tools" / "preview.py"
PAGE = REPO / "board" / "tasks-board.html"
FIXED_DATE = "2026-03-10"
NODE = shutil.which("node")


def read(path):
    return Path(path).read_text(encoding="utf-8")


def write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def env():
    e = dict(os.environ)
    e.pop("BOARD_CONFIG", None)
    e["PYTHONDONTWRITEBYTECODE"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    e["PYTHONUTF8"] = "1"
    return e


def run(script, *args, cwd):
    """Run a kit script with this Python; returns the CompletedProcess (text, utf-8)."""
    return subprocess.run([sys.executable, "-B", str(script), *map(str, args)], cwd=str(cwd), env=env(),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace", timeout=120)


def task_rows(tasks_md):
    return [l for l in read(tasks_md).split("\n") if re.match(r"^\| T\d+ \|", l)]


def repo_snapshot():
    out = set()
    for p in REPO.rglob("*"):
        if ".git" in p.relative_to(REPO).parts:
            continue
        out.add(p.relative_to(REPO).as_posix())
    return out


class TempBoard(unittest.TestCase):
    """Base class: a fresh temp folder per test, with the repo's file list checked before and after."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="board-test-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.before = repo_snapshot()
        self.addCleanup(self._repo_untouched)

    def _repo_untouched(self):
        self.assertEqual(repo_snapshot(), self.before, "a test wrote inside the repo")

    def board(self, name="board", shift=True):
        folder = self.tmp / name
        folder.mkdir(parents=True)
        args = [folder, "--date", FIXED_DATE] if shift else [folder, "--no-shift"]
        r = run(LOAD_SAMPLE, *args, cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return folder


class SampleBoardTests(TempBoard):
    def check_board(self, folder):
        r = run(SYNC, "check", cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(SYNC, "stale", cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.split(":", 1)[-1].strip(), "none", "stale printed: " + r.stdout)
        r = run(SYNC, "export", cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        docs = sorted((folder / "board" / "out" / "docs").glob("T*.json"))
        self.assertEqual(len(docs), len(task_rows(folder / "tasks.md")))
        self.assertGreater(len(docs), 0)
        for d in docs:
            self.assertEqual(json.loads(read(d))["id"], d.stem)

    def test_01_shifted_sample_checks_and_exports(self):
        self.check_board(self.board(shift=True))

    def test_01_unshifted_sample_checks_and_exports(self):
        folder = self.board(shift=False)
        self.assertEqual(read(folder / "tasks.md"), read(REPO / "sample" / "tasks.md"))
        self.check_board(folder)

    def test_01_shift_moves_dates_to_target_day(self):
        folder = self.board()
        brief = json.loads(read(folder / "state" / "brief-today.json"))
        self.assertEqual(brief["date"], FIXED_DATE)

    def test_08_space_and_non_ascii_folder_name(self):
        self.check_board(self.board(name="Mi tablero é ü 日本 board"))


class RoundTripTests(TempBoard):
    def test_02_import_changes_only_the_edited_row(self):
        folder = self.board()
        self.assertEqual(run(SYNC, "export", cwd=folder).returncode, 0)
        docs = folder / "board" / "out" / "docs"
        before = read(folder / "tasks.md").split("\n")
        target = docs / "T003.json"
        doc = json.loads(read(target))
        self.assertNotIn(doc["status"], ("Done", "Abandoned"))
        new_status = "Postponed" if doc["status"] != "Postponed" else "In Progress"
        doc.update(title="Renamed by the page test", status=new_status, dirty=True, editedFields=["title", "status"])
        inbox = self.tmp / "inbox"
        inbox.mkdir()
        write(inbox / "T003.json", json.dumps(doc, ensure_ascii=False))
        r = run(SYNC, "import", inbox, cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("T003", r.stdout)
        after = read(folder / "tasks.md").split("\n")
        self.assertEqual(len(before), len(after))
        diff = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual(len(diff), 1, "expected exactly one changed line, got %s" % diff)
        self.assertTrue(after[diff[0]].startswith("| T003 |"))
        self.assertIn("| Renamed by the page test |", after[diff[0]])
        self.assertIn("| " + new_status + " |", after[diff[0]])
        self.assertEqual(run(SYNC, "check", cwd=folder).returncode, 0)

    def test_02_clean_documents_are_ignored(self):
        folder = self.board()
        self.assertEqual(run(SYNC, "export", cwd=folder).returncode, 0)
        before = read(folder / "tasks.md")
        r = run(SYNC, "import", folder / "board" / "out" / "docs", cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read(folder / "tasks.md"), before)

    def test_02_check_rejects_nine_cells(self):
        folder = self.board()
        text = read(folder / "tasks.md").rstrip("\n")
        write(folder / "tasks.md", text + "\n| T099 | Nine cells only | Not started | Low | general | | notes | 2026-03-10 | 2026-03-10 |\n")
        r = run(SYNC, "check", cwd=folder)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("T099", r.stdout + r.stderr)

    def test_02_check_rejects_bad_date(self):
        folder = self.board()
        text = read(folder / "tasks.md").rstrip("\n")
        write(folder / "tasks.md", text + "\n| T099 | Bad due date | Not started | Low | general | 2026-13-45 | notes | 2026-03-10 | 2026-03-10 | |\n")
        r = run(SYNC, "check", cwd=folder)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("T099", r.stdout + r.stderr)
        self.assertNotEqual(run(SYNC, "export", cwd=folder).returncode, 0)


class JobScriptTests(TempBoard):
    def test_03_start_lock_finish(self):
        folder = self.board()
        r = run(PRECHECK, "start", cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("BUSY", r.stdout)
        self.assertIsInstance(json.loads(r.stdout), dict)
        self.assertTrue((folder / "state" / "run.lock").exists())
        again = run(PRECHECK, "start", cwd=folder)
        self.assertIn("BUSY", again.stdout)
        fin = run(PRECHECK, "finish", cwd=folder)
        self.assertEqual(fin.returncode, 0, fin.stdout + fin.stderr)
        self.assertFalse((folder / "state" / "run.lock").exists())
        third = run(PRECHECK, "start", cwd=folder)
        self.assertNotIn("BUSY", third.stdout)
        self.assertIsInstance(json.loads(third.stdout), dict)

    def test_03_seen_and_filed(self):
        folder = self.board()
        r = run(PRECHECK, "seen", "doc-a", "doc-b", cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.split(), ["doc-a", "doc-b"])
        r = run(PRECHECK, "filed", "doc-a", "2026-03-10_note.md", cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(PRECHECK, "seen", "doc-a", "doc-b", cwd=folder)
        self.assertEqual(r.stdout.split(), ["doc-b"])

    def test_03_efficiency_report_prints_json(self):
        folder = self.board()
        run(PRECHECK, "start", cwd=folder)
        run(PRECHECK, "finish", cwd=folder)
        for args in ([], ["30"]):
            r = run(EFFICIENCY, *args, cwd=folder)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIsInstance(json.loads(r.stdout), dict)


class PreviewAndPageTests(TempBoard):
    def build_preview(self):
        out = self.tmp / "site"
        r = run(PREVIEW, "--no-serve", "--out", out, cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((out / "index.html").is_file())
        return out / "index.html"

    def test_04_preview_writes_index_html(self):
        index = self.build_preview()
        html = read(index)
        self.assertIn("<script", html)
        # the page itself is embedded in the preview
        marker = re.search(r"<title>(.*?)</title>", read(PAGE), re.S)
        if marker:
            self.assertIn(marker.group(1).strip(), html)
        self.assertGreater(len(html), len(read(PAGE)) // 2)

    # preview.py reads the page and writes index.html as UTF-8 whatever the platform default is.
    def test_04_preview_under_non_utf8_default_encoding(self):
        e = env()
        e.update(PYTHONUTF8="0", PYTHONCOERCECLOCALE="0", LC_ALL="C", PYTHONIOENCODING="ascii:replace")
        out = self.tmp / "site-legacy"
        r = subprocess.run([sys.executable, "-B", str(PREVIEW), "--no-serve", "--out", str(out)], cwd=str(self.tmp), env=e,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        page = read(PAGE)
        sample = next(c for c in page if ord(c) > 127)
        self.assertIn(sample, read(out / "index.html"))

    def js_scripts(self, html):
        found = []
        for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", html, re.S | re.I):
            attrs, body = m.group(1), m.group(2)
            if re.search(r"\bsrc\s*=", attrs, re.I):
                continue
            t = re.search(r"\btype\s*=\s*[\"']?([^\"'\s>]+)", attrs, re.I)
            if t and t.group(1).lower() not in ("text/javascript", "application/javascript", "module"):
                continue
            if body.strip():
                found.append((body, bool(t and t.group(1).lower() == "module")))
        return found

    def node_check(self, html, label):
        scripts = self.js_scripts(html)
        self.assertGreater(len(scripts), 0)
        for n, (body, is_module) in enumerate(scripts):
            f = self.tmp / ("%s-%d.%s" % (label, n, "mjs" if is_module else "js"))
            write(f, body)
            r = subprocess.run([NODE, "--check", str(f)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               encoding="utf-8", errors="replace", timeout=60)
            self.assertEqual(r.returncode, 0, "%s script %d: %s" % (label, n, r.stderr))

    @unittest.skipUnless(NODE, "node is not on PATH")
    def test_07_page_scripts_parse(self):
        self.node_check(read(PAGE), "page")

    @unittest.skipUnless(NODE, "node is not on PATH")
    def test_07_preview_scripts_parse(self):
        self.node_check(read(self.build_preview()), "preview")


def new_row(tid="T099", title="Added by test", notes="notes"):
    return "| %s | %s | Not started | Low | general | | %s | 2026-03-10 | 2026-03-10 | |" % (tid, title, notes)


def append_row(folder, row):
    text = read(folder / "tasks.md").rstrip("\n")
    write(folder / "tasks.md", text + "\n" + row + "\n")


def inbox(tmp, *docs):
    d = Path(tmp) / "inbox"
    d.mkdir(exist_ok=True)
    for doc in docs:
        write(d / (doc["id"] + ".json"), json.dumps(doc))
    return d


class SyncSafetyTests(TempBoard):
    def test_02_import_rejects_empty_title_for_a_new_task(self):
        folder = self.board()
        before = read(folder / "tasks.md")
        r = run(SYNC, "import", inbox(self.tmp, {"id": "T050", "isNew": True, "dirty": True, "title": "   ", "status": "Not started"}), cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("T050", r.stdout)
        self.assertIn("empty title", r.stdout)
        self.assertEqual(read(folder / "tasks.md"), before)
        self.assertEqual(run(SYNC, "check", cwd=folder).returncode, 0)

    def test_02_import_keeps_old_title_when_edit_is_empty(self):
        folder = self.board()
        run(SYNC, "export", cwd=folder)
        doc = json.loads(read(folder / "board" / "out" / "docs" / "T003.json"))
        old_title = doc["title"]
        doc.update(title="  ", priority="Low", dirty=True, editedFields=["title", "priority"])
        r = run(SYNC, "import", inbox(self.tmp, doc), cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("title is empty", r.stdout)
        self.assertEqual(run(SYNC, "check", cwd=folder).returncode, 0)
        row = [l for l in task_rows(folder / "tasks.md") if l.startswith("| T003 |")][0]
        self.assertIn("| " + old_title + " |", row)

    def test_03_check_fails_on_a_row_with_leading_whitespace(self):
        folder = self.board()
        append_row(folder, "  " + new_row("T098"))
        r = run(SYNC, "check", cwd=folder)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("leading whitespace", r.stdout)
        self.assertRegex(r.stdout, r"line \d+")
        self.assertNotEqual(run(SYNC, "export", cwd=folder).returncode, 0)

    def test_04_export_refuses_summaries_state_and_foreign_folders(self):
        folder = self.board()
        summary = folder / "summaries" / "T001.json"
        before = read(summary)
        for target in ("summaries", "state"):
            r = run(SYNC, "export", "--out", target, cwd=folder)
            self.assertNotEqual(r.returncode, 0, target)
            self.assertIn("export refused", r.stdout + r.stderr)
        self.assertEqual(read(summary), before)
        mixed = folder / "mixed"
        mixed.mkdir()
        write(mixed / "notes.txt", "mine")
        write(mixed / "T777.json", "{}")
        r = run(SYNC, "export", "--out", "mixed", cwd=folder)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(read(mixed / "T777.json"), "{}")
        self.assertEqual(run(SYNC, "export", "--out", "fresh", cwd=folder).returncode, 0)
        self.assertEqual(run(SYNC, "export", "--out", "fresh", cwd=folder).returncode, 0)

    def test_05_import_keeps_a_backup_and_leaves_no_temp_file(self):
        folder = self.board()
        run(SYNC, "export", cwd=folder)
        before = read(folder / "tasks.md")
        doc = json.loads(read(folder / "board" / "out" / "docs" / "T003.json"))
        doc.update(title="Backup test", dirty=True, editedFields=["title"])
        self.assertEqual(run(SYNC, "import", inbox(self.tmp, doc), cwd=folder).returncode, 0)
        self.assertEqual(read(folder / "tasks.md.bak"), before)
        self.assertEqual([p.name for p in folder.glob("tasks.md.*.tmp")], [])

    def test_05_plan_warns_about_unimported_page_edits(self):
        folder = self.board()
        run(SYNC, "export", cwd=folder)
        board_copy = self.tmp / "boardcopy"
        shutil.copytree(str(folder / "board" / "out" / "docs"), str(board_copy))
        doc = json.loads(read(board_copy / "T002.json"))
        doc.update(title="Edited on the page", dirty=True, editedFields=["title"])
        write(board_copy / "T002.json", json.dumps(doc))
        r = run(SYNC, "plan", board_copy, cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("warning: T002", r.stdout)
        self.assertIn("import first", r.stdout)

    def test_06_import_fails_when_the_folder_is_missing(self):
        folder = self.board()
        before = read(folder / "tasks.md")
        r = run(SYNC, "import", self.tmp / "no-such-folder", cwd=folder)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not found", r.stdout + r.stderr)
        self.assertEqual(read(folder / "tasks.md"), before)

    def test_06_import_does_not_recreate_a_task_missing_from_tasks_md(self):
        folder = self.board()
        before = read(folder / "tasks.md")
        r = run(SYNC, "import", inbox(self.tmp, {"id": "T077", "dirty": True, "title": "Ghost", "status": "Done", "editedFields": ["status"]}), cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("skipped T077", r.stdout)
        self.assertEqual(read(folder / "tasks.md"), before)

    def test_10_check_fails_on_a_poc_with_a_full_stop(self):
        folder = self.board()
        append_row(folder, new_row("T097", notes="RACI: A. POC: Dr. Jane Smith. 2026-03-09 call: agreed."))
        r = run(SYNC, "check", cwd=folder)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("full stop", r.stdout)
        self.assertIn("T097", r.stdout)

    def test_10_poc_without_full_stops_passes(self):
        folder = self.board()
        append_row(folder, new_row("T097", notes="RACI: A. POC: Dr Jane Smith. 2026-03-09 call: agreed."))
        self.assertEqual(run(SYNC, "check", cwd=folder).returncode, 0)


class JobRobustnessTests(TempBoard):
    def test_07_malformed_card_is_skipped_by_start(self):
        folder = self.board()
        write(folder / "state" / "confirm-queue" / "bad.json", "[1]")
        r = run(PRECHECK, "start", cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIsInstance(json.loads(r.stdout), dict)
        self.assertIn("bad.json", r.stderr)

    def test_07_corrupt_processed_json_is_not_overwritten(self):
        folder = self.board()
        write(folder / "state" / "processed.json", '{"a": 1,')
        r = run(PRECHECK, "filed", "doc-z", "n.md", cwd=folder)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(read(folder / "state" / "processed.json"), '{"a": 1,')

    def test_07_naive_last_sweep_time_is_read_as_utc(self):
        folder = self.board()
        write(folder / "state" / "hourly-run.json", json.dumps({"last_sweep_at": "2026-03-10T08:00:00"}))
        r = run(PRECHECK, "start", cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIsInstance(json.loads(r.stdout), dict)

    def test_07_a_crash_after_the_lock_releases_it(self):
        folder = self.board()
        write(folder / "state" / "hourly-run.json", json.dumps({"last_run_date": 5}))
        r = run(PRECHECK, "start", cwd=folder)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((folder / "state" / "run.lock").exists())

    def test_08_efficiency_report_skips_bad_lines_and_cards(self):
        folder = self.board()
        state = folder / "state"
        good = json.dumps({"at": "2026-03-10T08:00:00+00:00", "seconds": 5})
        write(state / "run-log.jsonl", "garbage\n\n" + good + "\n[1]\n" + good + "\n")
        write(state / "confirm-queue" / "list.json", "[1]")
        write(state / "confirm-queue" / "opts.json", json.dumps({"id": "o", "createdAt": "2026-03-10T08:00:00Z", "answer": "confirm", "options": ["x"]}))
        write(state / "confirm-queue" / "origin.json", json.dumps({"id": "p", "createdAt": "2026-03-10T08:00:00Z", "origin": 3}))
        r = run(EFFICIENCY, "36500", cwd=folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["runs"], 2)
        self.assertEqual(out["run_log_lines_skipped"], 2)
        self.assertEqual(out["cards_skipped_as_malformed"], 3)


class PreviewHardeningTests(TempBoard):
    def test_09_html_comment_opener_in_data_is_escaped(self):
        folder = self.board()
        append_row(folder, new_row("T096", "Comment <!-- <script> test", "note with <!-- <script> and </script> inside"))
        r = run(PREVIEW, "--data", folder, "--no-serve", "--out", self.tmp / "site", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        html = read(self.tmp / "site" / "index.html")
        self.assertNotIn("<!-- <script>", html)
        self.assertNotIn("<!-- <script", html.split("window.claude", 1)[0])

    def test_09_bad_port_is_refused_with_a_message(self):
        for bad in ("abc", "0", "99999"):
            r = run(PREVIEW, "--port", bad, cwd=self.tmp)
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertIn("--port", r.stdout + r.stderr)

    def test_09_about_must_be_an_https_link(self):
        r = run(PREVIEW, "--no-serve", "--out", self.tmp / "s1", "--about", "javascript:alert(1)", cwd=self.tmp)
        self.assertNotEqual(r.returncode, 0)
        r = run(PREVIEW, "--no-serve", "--out", self.tmp / "s2", "--about", 'https://example.com/a"><b onmouseover=1>&x', cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        html = read(self.tmp / "s2" / "index.html")
        self.assertNotIn('"><b onmouseover', html)
        self.assertIn("&quot;&gt;&lt;b onmouseover", html)

    def test_09_card_without_id_is_skipped(self):
        folder = self.board()
        write(folder / "state" / "confirm-queue" / "noid.json", json.dumps({"title": "no id"}))
        r = run(PREVIEW, "--data", folder, "--no-serve", "--out", self.tmp / "site", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("noid.json", r.stderr)

    @unittest.skipUnless(os.name == "posix", "SIGTERM handling is checked on POSIX")
    def test_09_sigterm_removes_the_temp_folder(self):
        tmpdir = self.tmp / "tmpdir"
        tmpdir.mkdir()
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        e = env()
        e["TMPDIR"] = str(tmpdir)
        proc = subprocess.Popen([sys.executable, "-B", str(PREVIEW), "--port", str(port)], cwd=str(self.tmp), env=e,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        try:
            line = proc.stdout.readline()
            self.assertIn("http://localhost:%d/" % port, line)
            self.assertTrue(list(tmpdir.glob("board-site-*")))
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=20)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.stdout.close()
            proc.stderr.close()
        self.assertEqual([p.name for p in tmpdir.iterdir()], [])

    def test_09_load_sample_refuses_a_folder_with_meetings_or_a_brief(self):
        for name, make in (("meetings", lambda d: write(d / "meetings" / "mine.md", "x")), ("brief", lambda d: write(d / "state" / "brief-today.json", "{}"))):
            d = self.tmp / name
            d.mkdir()
            make(d)
            r = run(LOAD_SAMPLE, d, cwd=self.tmp)
            self.assertNotEqual(r.returncode, 0, name)
            self.assertFalse((d / "tasks.md").exists())

    def test_12_no_regex_lookbehind_in_the_page_or_the_preview(self):
        scripts = PreviewAndPageTests.js_scripts(None, read(PAGE)) + PreviewAndPageTests.js_scripts(None, read(PREVIEW).split('STUB = r"""', 1)[1].split('"""', 1)[0])
        self.assertGreater(len(scripts), 1)
        for body, _ in scripts:
            self.assertNotIn("(?<=", body)
            self.assertNotIn("(?<!", body)


class DocsTests(unittest.TestCase):
    def test_05_every_placeholder_is_named_in_setup(self):
        setup = read(REPO / "setup.md")
        for name in ("job/job-template.md", "board/brain-template.md"):
            names = set(re.findall(r"\{\{([A-Z][A-Z0-9_]*)\}\}", read(REPO / name)))
            names.discard("PLACEHOLDER")  # the generic word used in the template's own comment
            self.assertTrue(names, name)
            missing = sorted(n for n in names if "{{%s}}" % n not in setup and n not in setup)
            self.assertEqual(missing, [], "%s: placeholders not named in setup.md" % name)

    def test_06_sample_json_parses(self):
        files = sorted((REPO / "sample").rglob("*.json"))
        self.assertGreater(len(files), 0)
        for f in files:
            with self.subTest(file=f.relative_to(REPO).as_posix()):
                json.loads(read(f))

    def test_06_relative_markdown_links_resolve(self):
        link = re.compile(r"(?<!\!)\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)|!\[[^\]]*\]\(\s*<?([^)\s>]+)>?")
        md_files = [p for p in REPO.rglob("*.md") if ".git" not in p.relative_to(REPO).parts]
        self.assertGreater(len(md_files), 0)
        broken = []
        for md in md_files:
            text = re.sub(r"```.*?```", "", read(md), flags=re.S)
            text = re.sub(r"`[^`\n]*`", "", text)
            for m in link.finditer(text):
                target = m.group(1) or m.group(2)
                if re.match(r"^([a-z][a-z0-9+.-]*:|#|//)", target, re.I) or "{{" in target:
                    continue
                path = unquote(target.split("#", 1)[0].split("?", 1)[0])
                if not path:
                    continue
                dest = (REPO / path.lstrip("/")) if path.startswith("/") else (md.parent / path)
                if not dest.exists():
                    broken.append("%s -> %s" % (md.relative_to(REPO).as_posix(), target))
        self.assertEqual(broken, [], "broken relative links")


if __name__ == "__main__":
    unittest.main()
