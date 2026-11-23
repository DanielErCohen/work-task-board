# Security

## Reporting a problem

Report a security problem privately: on this repository's page open **Security**, then **Report a vulnerability**. Please do not open a public issue for it. You get an answer within seven days.

Examples of what counts: text from a mail, a chat message, a meeting note or a task that runs script on the board page; a link on the page that opens something other than what it shows; a script in the kit that writes outside the board folder; a way for text the job reads to make Claude send, post or publish without the owner's yes.

## What the kit does with your data

- The kit folder holds no personal data. Your tasks, notes, cards and morning page live in your own notes folder and on your own private page on claude.ai.
- The scripts use Python's standard library only and make no network calls. `tools/preview.py` serves the page on this computer only (`localhost`).
- The page escapes every text and link it shows. Text that the hourly job reads from mail, chat, notes and the calendar is treated as data, never as instructions, by the rules in `job/job-template.md`.
- What a connector reads goes to Claude, like anything you paste into a chat. Check your company's AI and data policy before you connect a work account.

## Supported version

Only the latest version on the `main` branch gets fixes. `update.md` brings an existing board up to it.
