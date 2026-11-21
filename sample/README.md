# sample: an invented board to try first

Every person, company, product and figure here is invented. `tools/load_sample.py` copies this folder into a board folder with every date moved so that the sample day is today; it leaves out this file and the other `README.md` files.

| Item | What it is |
|---|---|
| [tasks.md](tasks.md) | Ten tasks, one in every status. |
| `summaries/` | The side-panel summary of each task, `T001.json` to `T010.json`. |
| `state/confirm-queue/` | Five cards: a drafted message, a comparison table, free time slots and two plain questions. |
| `state/brief-today.json` | The morning brief of the sample day. |
| `state/setup.json` | The setup document of the sample board: six steps done and four open, so the welcome and the Setup panel have something to show. It also holds the texts of the ten steps that a real setup copies. The sample loader leaves it out. |
| `state/sweep-sources.json` | The shape of the file that lists what the job reads in Gmail and Slack. Its ids are placeholders; the setup writes the real file. |
| `board.config.json` | The config of the sample board. |
| [meetings/](meetings/README.md) | Two filed meeting notes that the tasks link to. |
