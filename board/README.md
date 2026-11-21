# board: the page, the sync script and the rules template

| File | What it is for |
|---|---|
| `tasks-board.html` | The page. One config block at the top holds your name, the title, the default category, the statuses and `pointsShown` (how many points a meeting row shows per group before it folds the rest). |
| `sync_tasks.py` | Prepares the files that go from `tasks.md` to the page's database and applies the page's edits to `tasks.md`. Claude runs it; you do not need to. |
| [brain-template.md](brain-template.md) | The rules for how Claude works on your board, with placeholders the setup fills from your answers. It becomes `BRAIN.md` in your board folder. |
