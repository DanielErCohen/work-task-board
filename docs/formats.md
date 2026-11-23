# Formats

The four records the board is built from. Every example below is taken from `sample/`, which is invented; the longer ones are shortened.

## Task row (`tasks.md`)

One line per task in one Markdown table: keep all rows together, with headings and other text above or below the table. Ten cells, in this order:

| Cell | Field | Rule |
|---|---|---|
| 1 | ID | `T` and three digits, counting up: `T001`. |
| 2 | Title | Plain words, starts with a verb. |
| 3 | Status | One of: In Review, In Progress, Postponed, Pending others, Planning, Not started, Done, Abandoned. The page shows In Progress as "Working on now" and Postponed as "Started, postponed". A board with its own statuses lists them in `board.config.json` and in the page's config block; the two lists must match. |
| 4 | Priority | Critical, High, Medium or Low. |
| 5 | Category | One of your work areas, or `general`. At most 40 characters. |
| 6 | Due | `YYYY-MM-DD` or empty. For a Postponed task this is the restart date. |
| 7 | Notes | See below. Everything that is text goes here. |
| 8 | Opened | `YYYY-MM-DD`. |
| 9 | Last changed | `YYYY-MM-DD`. |
| 10 | Closed | `YYYY-MM-DD` when the status is Done or Abandoned, otherwise empty. |

The notes cell, in order:

1. Optional owner markers: `RACI: A, I. POC: Full Name.` RACI is your own role on the task (Responsible, Accountable, Consulted, Informed). POC is the point of contact: a full name written without full stops.
2. Optional people marker: `With: Full Name (owe); Other Name (waiting).` The kinds are `owe` (you owe them), `waiting` (they owe you) and `discuss`. The By person tab reads it.
3. Dated notes, newest first. Each starts `YYYY-MM-DD source: text`. Notes are separated by ` /  / `, and the first older one is introduced by `Earlier evidence retained:`.
4. Inside a note, three things become references. `[[note-file-name]]` names a note in a folder listed under `link_roots`; it opens as a link when `link_base` is set. A file path in backticks that ends in md, html, json, csv, py or xlsx becomes a file reference. A task ID such as `T004` opens that task. A sentence that starts with `Next:`, `Open:`, `Blocked:` or `Waiting on:` shows up under Additional details when the task has no summary.

A cell holds no pipe character and no line break. `python3 board/sync_tasks.py check` verifies every row; run it after every edit.

The two header lines of the table, then an example row:

```
| ID | Title | Status | Priority | Category | Due | Notes | Opened | Last changed | Closed |
|----|-------|--------|----------|----------|-----|-------|--------|--------------|--------|
| T004 | Run the usability test of the new booking flow with Erin | Not started | Medium | discovery | 2026-03-20 | RACI: A. POC: Erin Bennett. With: Erin Bennett (discuss). 2026-03-05 weekly with Erin Bennett ([[2026-03-05_weekly-erin-megan]]): the test needs half a day with staging frozen; Erin prefers a morning. Open: which morning, and whether the clinic admin view is tested separately. | 2026-03-05 | 2026-03-05 | |
```

## Summary file (`summaries/<ID>.json`)

What the side panel shows above the updates log. Claude writes it from the task's notes and rewrites it when the notes change.

| Field | Rule |
|---|---|
| `id` | The task ID. |
| `description` | What the task is and what done looks like. Under 45 words. Editable on the page. |
| `decision.date` | `YYYY-MM-DD`. |
| `decision.kind` | `decision` for a real decision or agreed commitment, `update` when the notes hold none. |
| `decision.source` | A plain label: "Weekly with Erin Bennett". |
| `decision.text` | One or two sentences. |
| `decision.url` | An https link, `meeting:<note file name without .md>`, or empty. |
| `details` | Two to six one-sentence bullets, each starting with `Next:`, `Open:`, `Waiting on:`, `People:`, `Scope:`, `Numbers:`, `Risk:` or `Background:`. |
| `notesHash` | Set by `sync_tasks.py stamp <ID>`. It records which notes the summary was written from; `sync_tasks.py stale` lists open tasks whose summary is missing or older than their notes. |

Example:

```json
{
 "id": "T004",
 "description": "Run the usability test of the new booking flow with Erin Bennett. Done means the findings are in the research sheet and the top three problems have owners.",
 "decision": {"date": "2026-03-05", "kind": "decision", "source": "Weekly with Erin Bennett", "text": "The test happens on a morning with staging frozen.", "url": "meeting:2026-03-05_weekly-erin-megan"},
 "details": ["Open: which morning, and whether the clinic admin view is tested separately.", "People: Erin Bennett runs the test; Megan freezes staging."],
 "notesHash": "set by stamp"
}
```

## To confirm card (`state/confirm-queue/<id>.json`, board collection `confirm`)

One prepared decision. The file name is the `id`.

| Field | Rule |
|---|---|
| `id` | Lower-case words joined by hyphens, ending in the date. The same item keeps its id in every run. |
| `title` | Plain words, no task ID. |
| `question` | What it is and what is left to decide. Two sentences at most. |
| `recommendation` | What Claude would do and what confirming causes. |
| `recAction` | `add`, `merge`, `covered`, `drop` or `answer`. A label for the job and the weekly review; the page does not read it. |
| `lane` | A category, shown as a tag. |
| `relatedTask` | A task ID or empty. |
| `origin` | `meeting`, `email` or `chat`. |
| `meeting` | A plain source label with the date: "Chat with Erin Bennett, 2026-03-09". |
| `sourceUrl` | An https link to the source, or empty. |
| `sourceAt` | When the source happened, UTC ISO time. Optional. |
| `context` | One or two sentences placing the item in its day. Optional. |
| `urgent` | `true` only for a deadline today. |
| `dueBy`, `priority`, `urgencyNote` | The date a decision is needed, 1 to 3, and at most six words of reason. The page sorts open cards by `urgent`, `dueBy`, `priority`, then age. |
| `slot` | Where the card sits on the page: `now`, `meeting` or `unblock`. Without it the page decides: a card whose `person` has a row that day goes to that row; an `urgent` card, or one whose `dueBy` has come, goes to Now; the rest go to Unblock others. |
| `person` | The `name` of the brief entry the card belongs to, exactly as written there. Optional. |
| `kind` | `approve` (one click decides), `send` (you send something yourself) or `think` (read or judge first). Shown as a tag. Optional. |
| `unblocks` | Under ten words on what your answer starts. Shown on cards in Unblock others. Optional. |
| `prepared` | What Claude checked, one line each. Shown under "What I checked". |
| `visual` | A list of blocks; see below. |
| `ready`, `needs` | 0 to 100, and the things only you can supply beyond picking an option. |
| `options` | Two or three of `{key, label, detail, recommended}`, four on a message card. Without options the page offers Confirm and Drop it. |
| `state` | `open`, then `answered` (set by the page), then `applied` (set by the job). |
| `answer`, `choice`, `comment`, `answeredAt` | Written by the page. `answer` is `confirm` (with `choice` set to an option key), `change` (a comment alone, or Other) or `drop`. |
| `appliedAt`, `result` | Written by the job: when it applied the answer and one sentence on what changed. |
| `createdAt`, `preparedAt`, `updatedAt` | UTC ISO times. |
| `boardSync` | `pending` while the local file is newer than the board copy. Local file only. |

Visual blocks, by `type`:

| Type | Fields | Use |
|---|---|---|
| `draft` | `title`, `to`, `text` | A message ready to send or copy. |
| `table` | `title`, `columns`, `rows` (lists of cells) | A comparison. A cell that holds one of these words is drawn as a coloured tag: `yes`, `no`, `partly`, `maybe`, `done`, `open`, `free`, `taken`, `now`, `next`. |
| `slots` | `title`, `weeks` (column heads), `rows` of `{key, label, note, cells}`; a cell is `free`, `taken`, `maybe`, or one of the tag words of `table` | Scheduling. |
| `timeline` | `title`, `points` of `{when, state, label}` with state `done`, `now` or `next` | A sequence of events. |
| `bars` | `title`, `unit`, `rows` of `{label, value, note}` | Counts. |
| `bullets` | `title`, `items` | A short list. |

Example (the plain form; `sample/state/confirm-queue/` has one card for each of draft, table and slots):

```json
{
 "id": "staging-login-repair-2026-03-10",
 "title": "Track the broken staging login as a task?",
 "question": "Erin Bennett wrote on 2026-03-09 that the staging login fails for her test account, which blocks her usability test. Nobody was named to fix it and no date was set.",
 "recommendation": "Add it as a Low priority delivery task with Erin as point of contact. Confirm adds the row; Drop it leaves it in the chat.",
 "recAction": "add", "lane": "delivery", "relatedTask": "", "origin": "chat",
 "meeting": "Chat with Erin Bennett, 2026-03-09", "sourceUrl": "",
 "urgent": false, "dueBy": "", "priority": 3, "urgencyNote": "",
 "state": "open", "answer": "", "choice": "", "comment": "", "answeredAt": "", "appliedAt": "", "result": "",
 "createdAt": "2026-03-10T07:46:00Z"
}
```

## Morning brief (`state/brief-today.json`, board document `brief/today`)

Written by the first run of the day. The page shows it while its day (`dayDate`, or `date` when that is missing) is today or still to come; without a current brief it picks three tasks by due date and priority and lists the tasks due within seven days.

| Field | Rule |
|---|---|
| `date` | `YYYY-MM-DD`, the day the brief is for. |
| `generatedAt` | UTC ISO time. |
| `dayDate` | `YYYY-MM-DD`, the day the meeting rows are for. Today on the morning run. |
| `reminders` | Up to three one-sentence lines on what is specific to the day. Shown in a box above everything else. |
| `note` | The first reminder, or empty. Shown when `reminders` is missing. |
| `top` | Up to three of `{taskId, title, whyShort, nextShort, why, next}`. The page shows the three titles as its Focus line; the short and long pairs stay in the file for the job's report. |
| `people` | The day's meetings in time order: `{name, meeting, start, end, when, with, note, met, owe, ask, decide}`. `start` and `end` are `HH:MM`. An entry whose three lists are empty shows as a plain row with `note` or "nothing prepared". `with` lists the full names of a group meeting. |
| `people[].owe`, `ask`, `decide` | Lists of `{short, text, taskId, confirm}`. `short` is a label of three to eight words, `text` is one or two sentences, `confirm` is `true` when the item is an open To confirm card. |
| `people[].met` | `true` after today's meeting with that person was filed; the page shows "Met", and open cards about that person leave the row. |
| `deadlines` | Up to five outside dates: `{date, title, yours: [{text, taskId}], waiting: [{who, text, taskId}]}`. `yours` is what you must do for it, `waiting` what others owe. Without it the page lists the tasks due within seven days. |

Example:

```json
{
 "date": "2026-03-10",
 "dayDate": "2026-03-10",
 "generatedAt": "2026-03-10T07:46:00Z",
 "reminders": ["The monthly metrics Steve Walker asked for are a day late; the weekly is at 14:00."],
 "note": "The weekly with Steve Walker is today at 14:00, and the monthly metrics he asked for are a day late.",
 "top": [
  {"taskId": "T010", "title": "Prepare the monthly product metrics for Steve",
   "whyShort": "A day late, weekly at 14:00", "nextShort": "Pull three figures; Claude drafts the page",
   "why": "Steve Walker asked for the page before the weekly, which is today at 14:00, and the due date was 2026-03-09.",
   "next": "Pull activation, retention and no-show rate from the analytics export; Claude can draft the page once you paste the three figures."}
 ],
 "people": [
  {"name": "Erin Bennett", "meeting": "Design check-in, Erin and Megan", "start": "09:30", "end": "10:00", "when": "today, 09:30",
   "owe": [{"short": "Answer on the staging login", "text": "She reported the broken login on 2026-03-09 and has no reply yet.", "confirm": true}],
   "ask": [],
   "decide": [{"short": "Morning for the usability test", "text": "Three mornings are free on both calendars; the first is 2026-03-16.", "taskId": "T004", "confirm": true}]},
  {"name": "Josh Reed", "meeting": "Booking flow walk-through", "start": "11:00", "end": "11:30", "when": "today, 11:00", "owe": [], "ask": [], "decide": []}
 ],
 "deadlines": [
  {"date": "2026-03-13", "title": "Online rescheduling launch",
   "yours": [{"text": "Two test reschedules, one on a phone and one on a laptop", "taskId": "T002"}],
   "waiting": [{"who": "Josh Reed", "text": "the default setting fix", "taskId": "T002"}]}
 ]
}
```

## Setup document (`state/setup.json`, board document `setup/state`)

What the setup settled and what is still open. The page reads it for the welcome on the first open and for the Setup button; a board without it shows neither.

```
{
 "owner": "Megan",
 "purpose": "Keep track of what I promised in meetings.",
 "folder": "Documents/work-notes/task-board",
 "createdAt": "2026-03-10",
 "welcomed": false,
 "steps": [
  {"id": "calendar", "title": "Calendar", "adds": "Your meetings appear at the top of the page.", "state": "done",
   "kind": "say", "say": "Connect my calendar to my board", "detail": "Your own calendar"},
  {"id": "limits", "title": "Limits", "adds": "What Claude may never do without your yes.", "state": "todo",
   "kind": "answer", "question": "Is there anything else Claude may never do without your yes?",
   "usual": "The usual list: send, post, publish, create a ticket, send an invite, change a task's status.",
   "answer": "", "answeredAt": ""}
 ]
}
```

- `owner` is the name Claude calls the person, `purpose` is their own sentence, `folder` is the board folder the way they would recognise it. The page sets `welcomed` when the welcome is closed.
- A step's `state` is `todo`, `answered` or `done`. `kind` is `say` (the person says the sentence in `say` to Claude; `where` names a connector to switch on first) or `answer` (the person types on the page; `usual` is the choice in force until they do).
- The page writes `answer`, `answeredAt` and `state: "answered"`, or `state: "done"` with `detail: "The usual"`. Claude applies an answered step and sets it to `done` with a `detail` of a few words.
- The file also holds `answers`: every answer and usual choice of the setup, by question number (1 to 19). Question 18 is an object: `use`, `calendar`, `mail`, `chat`, `notes` and `readable` (`setup.md`, question 18). A file without it is read as work use with Google Calendar, Gmail, Gemini notes by mail and Slack. It stays in the file and is not written to the page.
- The page writes only to the board document. Claude reads that document first, takes its changes into the file, and writes back `steps` alone.
- The steps (up to ten) and what each changes are in `setup.md`, "Later steps".

## The page's database

| Collection | Document id | Written by |
|---|---|---|
| `setup` | `state` | The setup and later steps; the page (the welcome, an answer typed in the Setup panel); the job when it applies an answer. |
| `tasks` | The task ID | `sync_tasks.py export` plus a board write; the page on an edit (`dirty: true`, `editedFields` listing what it changed, and `isNew: true` for a task created on the page). |
| `confirm` | The card `id` | The job (new and applied cards); the page (the answer). |
| `brief` | `today` | The job, on the first run of the day. |
| `prep` | `p-<hash>` | The page, when you tick a point in a meeting row as discussed. The task behind it does not change. |

A page edit reaches `tasks.md` through `sync_tasks.py import`. It applies only documents with `dirty: true`, and of those only the fields named in `editedFields`. So when the same task changed in both places, the page wins for the fields it changed and `tasks.md` keeps the rest, such as a note added in the meantime. A task created on the page whose ID was taken in `tasks.md` in the meantime is imported under the next free ID. Import prints the IDs to write back to the board ("clear dirty on"); the dirty mark stays until that write.

## Syncing by hand

"Sync the board" means these three steps, run from the board folder:

1. Pull the page's edits: query the `tasks` collection for documents with `dirty == true`, save them to a scratch folder, and run `python3 board/sync_tasks.py import <that folder>`.
2. Push `tasks.md`: run `python3 board/sync_tasks.py export`, list the `tasks` collection to a scratch folder, run `python3 board/sync_tasks.py plan <that folder>`, and write every task it lists as new or changed, plus every ID import printed after "clear dirty on", from `board/out/docs/` to the board.
3. Say how many tasks came from the page and how many went to it.
