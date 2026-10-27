# Scouting a sub

A sub must beat the skill it replaces, not just exist. Run every check. One failure rules the candidate out.

1. **Same job.** Open the candidate's `SKILL.md` (from its skills.sh page or GitHub repo). It does the job you named, not a neighbour of it.
2. **Proven.** 1,000+ installs on skills.sh. Below 100, rule it out.
3. **Trusted source.** An official org (`anthropics`, `vercel-labs`, `microsoft`, the tool's own vendor) or a repo with real stars and a known maintainer.
4. **Alive.** A commit in the last six months.
5. **Safe.** Read every script it ships. Rule out anything that pipes a download into a shell, sends files or environment data off the machine, or asks for credentials it does not need.
6. **Better, head to head.** Name what it does that the current skill does not: sharper steps, a real script, wider coverage, fewer tokens. "More installs" alone is not better.
7. **Lean.** Its description costs no more context than the skill it replaces, unless the extra power is worth it. Say the trade.

Report each sub as: `name · installs · source · the one thing it does better`.
