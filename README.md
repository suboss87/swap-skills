# swap-skills

**Bench the skills you never use. Sub in better ones.**

You installed a skill for every problem you ever had. Now your agent carries all of them, every turn, whether it needs them or not. Most of them never fire.

When I ran this on my own machine:

```
133 skills | ~8695 tokens always loaded | 115 never used | 115 idle 60d | 29 with problems
```

115 skills sat in my agent's context on every turn. Not one shows a single call in my agent history.

`swap-skills` treats your skills like a team roster. It pulls the real stats from your agent's history, calls every skill, benches the dead weight, merges the duplicates, and scouts a better public skill for every job still worth doing. You say yes. It makes the moves. Everything comes back with one command.

## Install

```bash
npx skills add suboss87/swap-skills -g
```

Or as a Claude Code plugin:

```
/plugin marketplace add suboss87/swap-skills
/plugin install swap-skills@swap-skills
```

Then call it. In Claude Code type `/swap-skills`. In Codex type `$swap-skills`.

It costs zero context until you call it. A skill that cleans up skill bloat should not add to it.

## What happens

1. **Stats.** A scan reads every skill folder (Claude Code, `npx skills`, Codex, Cursor, Gemini, plugins, the current project) and every Claude Code and Codex transcript. Per skill: uses, last use, tokens it costs every turn, where it came from, what is broken.
2. **Calls.** Every skill gets one verdict.

   | | Verdict | Meaning |
   |---|---|---|
   | ✅ | KEEP | Earns its place. |
   | 🪑 | BENCH | Never used, no job to tie it to. |
   | 🧩 | MERGE | Two skills, one job. Keep the stronger. |
   | 🔁 | SWAP | Good job, weak skill. A better one exists. |
   | 🔧 | FIX | Worth keeping, but broken. |

3. **Scouting.** For every SWAP, it searches [skills.sh](https://skills.sh) and vets each candidate: same job, 1,000+ installs, trusted source, recent commits, scripts read for anything unsafe, and a clear reason it beats what you have.
4. **Review in rounds.** One round per verdict, biggest win first. Every round has a recommendation, so "yes" is enough.

   ```
   🪑 BENCH · 14 skills · ~2,100 tokens back every turn

   | # | Skill      | Uses (60d) | Last used | Tokens | Why                         |
   |---|------------|------------|-----------|--------|-----------------------------|
   | 1 | old-deploy | 0          | never     | 210    | Duplicates deploy-checklist |

   ➡️ Bench all 14. Reply "yes", or list the numbers to keep.
   ```

5. **Moves and scoreboard.** Benches, installs and fixes run only for what you accepted. A fresh scan shows skills and tokens before and after.

## Nothing gets deleted

Benched skills move to `~/.swap-skills/bench/` with a manifest. Skills installed with `npx skills` also leave the lock file, so an update does not quietly bring them back. The skill ends every session with the exact undo line. Or restore any time from the installed skill folder (`~/.agents/skills/swap-skills` after `npx skills add -g`):

```bash
S=~/.agents/skills/swap-skills/scripts
python3 $S/bench.py back --all          # everything
python3 $S/bench.py back <skill-name>   # one skill
python3 $S/bench.py list                # what is on the bench
```

Plugin skills are never moved. The skill disables the plugin instead.

## Run the scan on its own

No agent needed. Python 3.8+, standard library only, read-only:

```bash
python3 skills/swap-skills/scripts/roster.py            # table
python3 skills/swap-skills/scripts/roster.py --json -   # full JSON
python3 skills/swap-skills/scripts/roster.py --days 90  # wider window
```

## Good to know

- Usage comes from the transcripts your agents still keep. Zero uses means no evidence, not proof. The skill says so and asks you about jobs it cannot see.
- Token cost is an estimate: name plus description, about four characters per token. Skills with `disable-model-invocation: true` cost zero.
- Works with Claude Code and Codex history today. Other agents' skill folders are scanned, but not their history yet. Pull requests welcome.

## License

MIT
