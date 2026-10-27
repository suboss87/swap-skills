---
name: swap-skills
description: Bench the skills you never use, sub in better ones. A roster review for your agent.
disable-model-invocation: true
---

Treat the installed skills as a **roster**. Every skill on it costs context on every turn, so each one earns its place or goes to the **bench**. Your job is a coach's: read the stats, cut dead weight, merge players who do the same job, and **scout** a stronger **sub** for every job still worth doing.

Facts are your job. Decisions are the user's. Nothing leaves the roster without a "yes", and nothing is ever deleted: benched skills move aside and come back with one command.

## 1. Pull the stats

Run the roster scan from the user's working directory, so project skills count too. `scripts/` sits next to this file:

```bash
python3 <skill-dir>/scripts/roster.py --json /tmp/swap-skills-roster.json --days 60
```

It reads every skill folder (Claude Code, claude.ai synced skills, `npx skills`, Codex, Cursor, Gemini, plugins, this project) and every Claude Code and Codex transcript. For each skill it reports uses, last use, always-loaded token cost, source, and problems. Read the JSON, not just the table. Transcripts only cover what the logs still hold, so zero uses means "no evidence", not proof. Say so once.

Done when you hold the whole roster: every skill, its numbers, and the overlap hints.

## 2. Call every skill

Give each skill exactly one verdict:

| Verdict | When |
|---|---|
| **KEEP** | Used in the window, or a job the user clearly still does. |
| **BENCH** | No use in the window and no job you can tie it to. Bench the zero-use, high-token ones first. |
| **MERGE** | Two or more skills do one job. Keep the strongest, bench the rest. Read both bodies before you pick. |
| **SWAP** | The job matters, but the skill is weak: stale, broken, thin, or beaten by a better public skill. Goes to scouting. |
| **FIX** | Problems the scan flagged (broken symlink, missing description, copies that differ) on a skill worth keeping. |

Judge overlap from what the skills do, not from the hint scores: the hints only point at pairs to read. A skill with `disable-model-invocation` costs zero tokens, so it needs a stronger reason to bench. Plugin skills are benched by disabling the plugin, which takes every skill in it, so call them per plugin.

Done when every skill on the roster carries a verdict and a one-line reason grounded in the stats.

## 3. Scout the subs

For every SWAP and every MERGE cluster, name the job in two to four words and search:

```bash
npx -y skills find "<job>" < /dev/null
```

Vet each candidate with [SCOUTING.md](SCOUTING.md) before you put it in front of the user. Only a candidate that passes every check becomes a sub. If none passes, the verdict falls back to KEEP or BENCH. Say which.

Done when every SWAP has a vetted sub or an honest "nothing better found".

## 4. Run the review in rounds

Show the user one round per verdict group, biggest win first: BENCH, then MERGE, then SWAP, then FIX. KEEP gets one summary line. Format a round like so:

```
🪑 **BENCH** · 14 skills · ~2,100 tokens back every turn

| # | Skill | Uses (60d) | Last used | Tokens | Why |
|---|---|---|---|---|---|
| 1 | old-deploy | 0 | never | 210 | Duplicates deploy-checklist |

➡️ Bench all 14. Reply "yes", or list the numbers to keep.
```

Use 🔁 **SWAP** rows of `current → sub (installs, source)`, 🧩 **MERGE** rows of `keep ← bench`, 🔧 **FIX** rows of `skill: problem → fix`. Word every round so "yes" accepts your recommendation. Wait for the answer before the next round.

## 5. Make the moves

Only for the rows the user accepted:

- **Bench:** `python3 <skill-dir>/scripts/bench.py out <path> ...`, with each path from the skill's `copies` in the scan, so no copy stays behind.
- **Plugin:** `claude plugin disable <plugin>`.
- **claude.ai synced skill** (source `claude.ai sync`): the user turns it off in claude.ai Settings > Capabilities > Skills. Give them the list.
- **Sub in:** `npx -y skills add <owner/repo@skill> -g -y`, then bench the skill it replaces.
- **Fix:** edit the frontmatter or relink, then rerun the scan.

Rerun the scan and finish with a scoreboard: skills before and after, always-loaded tokens before and after, subs signed, and the undo line:

```bash
python3 <skill-dir>/scripts/bench.py back <session>   # or: back --all, back <skill-name>
```

The session is done when every accepted move is made, the fresh scan confirms it, and the user has the undo line.
