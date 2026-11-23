# job: the hourly job

| File | What it is for |
|---|---|
| [job-template.md](job-template.md) | The hourly job, with placeholders the setup fills. Meeting notes, the twice-daily read of mail and chat (Gmail and Slack by default), the calendar and the weekly review are optional blocks. It becomes `job/SKILL.md` in your board folder. |
| `scripts/hourly_precheck.py` | Lets an hour with nothing new stop at once, and keeps two runs from writing at the same time. |
| `scripts/efficiency_report.py` | Counts what the queue of cards produced in a week, for the weekly review. |
