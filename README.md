# Work task board kit

A private task board that Claude keeps for you. You open one page in the morning and see what waits on you today, who you meet and what to raise with each person, and the decisions Claude has already prepared for your yes or no. This folder is the kit that builds your own copy. Claude sets it up by asking you questions; you write no code and need no technical knowledge.

![The board in a desktop browser: the Now block with two reminders and one card, Unblock others, the day's three meetings with the first one opened, two deadlines and the Focus line.](docs/img/board-desktop.png)

Every person, company and figure in the picture is invented.

## Set it up

1. Download the kit: on this repository's page press **Code**, then **Download ZIP**, and double-click the ZIP file so you have the folder `work-task-board-main`. On Windows, right-click the ZIP file and choose **Extract All** instead; a double-click only opens it. Leaving it in your Downloads folder is fine. If you use git, clone the repository instead.
2. In the Claude desktop app, open the Code tab, start a new session (**+ New**), choose a folder for it (your Documents folder is fine; Claude makes its own folders inside) and paste this one line:

> Read setup.md in the work-task-board folder I downloaded and set up my work board. Interview me first, one question at a time, and build nothing until I confirm your summary.

On a Mac, the app may ask whether Claude can open your Downloads or Documents folder: choose **Allow**, or Claude cannot read the kit. If you declined, switch it on in System Settings, Privacy & Security, Files and Folders, under Claude, and paste the line again.

When Claude cannot find the folder, it says so and stops. Paste the line again with the folder's full path in place of "the work-task-board folder I downloaded".

What happens after you paste it:

1. Claude finds the kit folder and works from it. When the kit sits in a git repository, Claude copies it to a working folder first, so the repository stays as it is.
2. It asks three questions (your name, what the board is for, how you want to start) and offers one connection, your calendar, so your page shows today's meetings from the start. You can stop at any point: say "that's enough" and it goes on with what you gave and the usual choice for the rest.
3. It reads back what it will build. Nothing is built until you confirm that list.
4. It builds your board folder and your private page, then asks once more before it switches on the hourly job.
5. Your page welcomes you by name. Its **Setup** button lists what is still open, such as your mail, your chat, the people you work with and your limits, and how to add each one when you want it.

To look before you answer anything, ask Claude to "show me the sample board first". It opens the invented sample on your own computer and publishes nothing.

## What you get

- **One page that follows your day.** At the top: **Now** (reminders and the decisions a date depends on), **Unblock others** (quick answers that let someone else start work), **The day** (one row per meeting from your Google Calendar, with what you owe, what to ask and what to decide together), **Deadlines** and your three tasks to **Focus** on. Below it, every task, grouped and searchable.
- **Decisions prepared for you.** Each one arrives as a card: a drafted message, a comparison table, free time slots or a plain question, with a recommendation. You pick an option and press Send.
- **A task list in plain text.** One table in a file called `tasks.md`, in your own notes folder. The page shows a copy of it. Each task opens to a description, the last decision, its history and its sources.
- **An Ask Claude box on the page.** You add, change or close a task by writing one sentence.
- **An hourly job on your computer.** It files your Gemini meeting notes, reads Gmail and Slack twice a day for requests and promises, checks your calendar, applies the answers you gave on the page and writes the morning's page. It reads, files and prepares. It never sends, posts or publishes; a message you approve goes out from your next chat with Claude, or stays a text for you to copy when you prefer to send everything yourself. It runs while the Claude app is open and your computer is awake.
- **A rules file in your words.** `BRAIN.md` holds how Claude works for you: prepare first, ask second, and never act on the list you set without your yes. The setup writes it from your answers, and you can change it at any time.

## What is checked for you

You do not have to check any of this yourself. The setup tests each item on your computer and tells you in one line what it found.

| What the board uses | In plain words | If it is missing |
|---|---|---|
| Claude Code in the Claude desktop app, signed in | The app you paste the line into | The setup cannot start |
| A page with its own data store | Claude can publish a private page on claude.ai that only you can open (Claude calls it an artifact) and that keeps your tasks in a small database | The setup stops and says so; the board cannot work |
| Ask Claude on the page | The page's permission to call Claude | The page shows a New task button instead; the rest works |
| A scheduled task | A prompt Claude Code runs by itself at set times | You start the job by saying "run the board job" |
| Python 3.9 or later | The language the kit's small scripts are written in; Claude runs them for you | On a Mac without it, macOS offers to install Apple's command line developer tools, which include it: choose Install, then Agree, and tell Claude when it has finished. On Windows, install it from python.org before you start. Otherwise the setup stops and tells you what to install |
| Google Calendar, Gmail and Slack connected to Claude | The links (connectors) that let Claude read them; you switch them on in the Claude app under Customize, then Connectors | Each one switches on a part of the job; the board works without them, and the meeting rows at the top stay empty without the calendar |

## What stays private

Your tasks, notes, cards and morning page live in your own notes folder and in your own private page. The kit folder holds none of it, so it can be shared as it is.

## What is in the folder

| Item | What it is for |
|---|---|
| [setup.md](setup.md) | The instructions Claude follows to build your board: a first sitting of three questions and one connection, the full list of 17 questions, and the later steps behind the page's Setup button |
| [update.md](update.md) | For a board that already exists: the instructions Claude follows to bring it to this version of the kit |
| [versions-and-tests.md](versions-and-tests.md) | What changed in each version, what has been tested and what has not |
| [board/](board/README.md) | The page, the script that keeps the page and `tasks.md` in step, and the template of the rules file |
| [job/](job/README.md) | The template of the hourly job and its two helper scripts |
| [skill/](skill/README.md) | The template of a "sync the board" command for when you edit `tasks.md` by hand |
| [docs/](docs/README.md) | The formats of a task row, a task summary, a card and the morning page, and three pictures of the board |
| [sample/](sample/README.md) | Ten invented tasks, five cards and one invented day, to try the board before you use your own data |
| `tools/` | `preview.py` shows the page on your own computer and publishes nothing; `load_sample.py` copies the sample into a board folder with its dates moved to today |
| `LICENSE` | MIT |

How the author uses the board and why he built it: https://danielercohen.github.io/ai-pm/toolkit/work-task-board.html
