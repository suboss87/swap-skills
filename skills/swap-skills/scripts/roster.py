#!/usr/bin/env python3
"""Build the skill roster: every installed skill, its context cost, its usage, its problems.

Read-only. Python 3.8+, standard library only.

  python3 roster.py                 # table on stdout
  python3 roster.py --json out.json # full roster as JSON (the skill reads this)
  python3 roster.py --days 90       # usage window (default 60)
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
CWD = Path.cwd()

# (label, directory). Each directory holds <skill>/SKILL.md.
ROOTS = [
    ("claude", HOME / ".claude" / "skills"),
    ("agents", HOME / ".agents" / "skills"),
    ("codex", HOME / ".codex" / "skills"),
    ("cursor", HOME / ".cursor" / "skills"),
    ("gemini", HOME / ".gemini" / "skills"),
    ("project-claude", CWD / ".claude" / "skills"),
    ("project-agents", CWD / ".agents" / "skills"),
]
PLUGIN_CACHE = HOME / ".claude" / "plugins" / "cache"
# claude.ai syncs its skills into buckets here; Claude Code loads them as "anthropic-skills:<name>".
SYNCED = HOME / ".claude" / "skills" / "synced"
SYNCED_PREFIX = "anthropic-skills"
# Which agent loads which root, for per-agent context cost.
AGENT_OF = {
    "claude": "claude-code", "project-claude": "claude-code", "plugin": "claude-code",
    "claude-synced": "claude-code", "agents": "codex", "project-agents": "codex",
    "codex": "codex", "cursor": "cursor", "gemini": "gemini",
}
INSTALLED_PLUGINS = HOME / ".claude" / "plugins" / "installed_plugins.json"
LOCK_FILES = [HOME / ".agents" / ".skill-lock.json", CWD / "skills-lock.json"]
CLAUDE_LOGS = HOME / ".claude" / "projects"
CODEX_LOGS = HOME / ".codex" / "sessions"

TS_RE = re.compile(r'"timestamp":"([0-9T:\.\-]+Z?)"')
CLAUDE_SKILL_RE = re.compile(r'"name":"Skill","input":\{"skill":"([^"]+)"')
CLAUDE_CMD_RE = re.compile(r"<command-name>/?([^<\s]+)</command-name>")
CODEX_PATH_RE = re.compile(r"/([A-Za-z0-9_.:-]+)/SKILL\.md")
CODEX_CALL_MARKERS = ('"custom_tool_call"', '"function_call"', '"local_shell_call"')


def parse_frontmatter(text):
    """Return (dict, body). Handles simple YAML: key: value, folded > and | blocks."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw, body = text[3:end], text[end + 4:]
    data, key, buf = {}, None, []
    for line in raw.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            if key is not None and buf:
                data[key] = " ".join(buf).strip()
            buf = []
            key, val = m.group(1), m.group(2).strip()
            buf = [] if val in (">", "|", ">-", "|-", "") else [val]
        elif key is not None and line.strip():
            buf.append(line.strip())
    if key is not None and buf:
        data[key] = " ".join(buf).strip()
    for k, v in data.items():
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            data[k] = v[1:-1]
    return data, body


def load_lock():
    sources = {}
    for f in LOCK_FILES:
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        for name, info in (data.get("skills") or {}).items():
            sources[name] = {
                "source": info.get("source"),
                "installed_at": info.get("installedAt"),
                "updated_at": info.get("updatedAt"),
                "lock_file": str(f),
            }
    return sources


def enabled_plugins():
    """Merge enabledPlugins from user, project and local settings (later wins)."""
    state = {}
    for f in (HOME / ".claude" / "settings.json", CWD / ".claude" / "settings.json",
              CWD / ".claude" / "settings.local.json"):
        try:
            state.update(json.loads(f.read_text()).get("enabledPlugins") or {})
        except Exception:
            continue
    return state


def plugin_dirs():
    """Yield (plugin, skill_dir) for each installed, enabled Claude Code plugin."""
    try:
        installed = json.loads(INSTALLED_PLUGINS.read_text()).get("plugins") or {}
    except Exception:
        return
    enabled = enabled_plugins()
    for key, installs in installed.items():
        if enabled.get(key) is False:
            continue
        for inst in installs if isinstance(installs, list) else [installs]:
            if inst.get("scope") == "project" and inst.get("projectPath") not in (None, str(CWD)):
                continue
            skills = Path(inst.get("installPath", "")) / "skills"
            if skills.is_dir():
                for d in sorted(skills.iterdir()):
                    yield key.split("@")[0], d
            break


def inspect(label, d, plugin=None):
    entry = {
        "dir_name": d.name,
        "root": label,
        "path": str(d),
        "plugin": plugin,
        "is_symlink": d.is_symlink(),
        "problems": [],
    }
    try:
        entry["real_path"] = str(d.resolve(strict=True))
    except (FileNotFoundError, RuntimeError):
        entry["real_path"] = None
        entry["problems"].append("broken symlink")
        entry.update(name=d.name, description="", user_invoked=False, context_tokens=0, lines=0)
        return entry
    skill_md = d / "SKILL.md"
    if not skill_md.is_file():
        entry["problems"].append("no SKILL.md")
        entry.update(name=d.name, description="", user_invoked=False, context_tokens=0, lines=0)
        return entry
    text = skill_md.read_text(errors="replace")
    entry["hash"] = hashlib.sha1(text.encode()).hexdigest()[:12]
    fm, body = parse_frontmatter(text)
    name = fm.get("name") or d.name
    desc = fm.get("description", "")
    user_invoked = str(fm.get("disable-model-invocation", "")).lower() == "true"
    if not fm:
        entry["problems"].append("no frontmatter")
    if not fm.get("name"):
        entry["problems"].append("missing name")
    if not desc:
        entry["problems"].append("missing description")
    if len(desc) > 1024:
        entry["problems"].append("description over 1024 chars")
    if fm.get("name") and fm["name"] != d.name and plugin is None:
        entry["problems"].append("name differs from folder")
    if len(body.strip()) < 40:
        entry["problems"].append("near-empty body")
    entry.update(
        name=name,
        description=desc,
        user_invoked=user_invoked,
        # Always-loaded cost: name + description, ~4 chars per token. User-invoked skills cost nothing.
        context_tokens=0 if user_invoked else (len(name) + len(desc)) // 4 + 4,
        lines=text.count("\n") + 1,
        has_scripts=any(p.is_dir() for p in d.iterdir() if p.name in ("scripts", "bin")),
        modified=datetime.fromtimestamp(skill_md.stat().st_mtime, timezone.utc).isoformat(),
    )
    return entry


def scan_logs(days):
    """Count invocations per skill name from Claude Code and Codex transcripts."""
    cutoff = time.time() - days * 86400
    usage = {}

    def hit(name, ts, file_mtime, tool):
        u = usage.setdefault(name, {"total": 0, "window": 0, "last_used": None, "tools": set()})
        u["total"] += 1
        u["tools"].add(tool)
        when = file_mtime
        if ts:
            try:
                when = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
        if when >= cutoff:
            u["window"] += 1
        if u["last_used"] is None or when > u["last_used"]:
            u["last_used"] = when

    files = 0
    for root, tool in ((CLAUDE_LOGS, "claude-code"), (CODEX_LOGS, "codex")):
        if not root.is_dir():
            continue
        for f in root.rglob("*.jsonl"):
            files += 1
            mtime = f.stat().st_mtime
            try:
                with open(f, errors="replace") as fh:
                    for line in fh:
                        if tool == "claude-code":
                            if "Skill" not in line and "command-name" not in line:
                                continue
                            names = CLAUDE_SKILL_RE.findall(line)
                            # Slash commands typed by the user (skills and built-ins alike).
                            if '"type":"user"' in line:
                                names += CLAUDE_CMD_RE.findall(line)
                        else:
                            if "SKILL.md" not in line or not any(m in line for m in CODEX_CALL_MARKERS):
                                continue
                            if "apply_patch" in line or "*** Update File" in line or "*** Add File" in line:
                                continue  # editing a skill is not using it
                            names = set(CODEX_PATH_RE.findall(line))
                        if not names:
                            continue
                        m = TS_RE.search(line)
                        for n in names:
                            hit(n, m.group(1) if m else None, mtime, tool)
            except OSError:
                continue
    for u in usage.values():
        u["tools"] = sorted(u["tools"])
        if u["last_used"]:
            u["last_used"] = datetime.fromtimestamp(u["last_used"], timezone.utc).date().isoformat()
    return usage, files


def word_set(text):
    stop = {"the", "a", "an", "and", "or", "to", "of", "for", "use", "when", "user", "with", "in",
            "on", "is", "this", "that", "it", "as", "by", "be", "you", "your", "asks", "wants", "skill"}
    return {w for w in re.findall(r"[a-z][a-z0-9-]{2,}", text.lower()) if w not in stop}


def overlap_hints(skills, threshold):
    """Pairs whose descriptions share many words. Hints only: the agent judges real overlap."""
    seen = {}
    for s in skills:
        if s["description"] and s["name"] not in seen:
            seen[s["name"]] = (s["name"], word_set(s["name"] + " " + s["description"]))
    items = list(seen.values())
    pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (a, wa), (b, wb) = items[i], items[j]
            if a == b or not wa or not wb:
                continue
            score = len(wa & wb) / len(wa | wb)
            if score >= threshold:
                pairs.append({"a": a, "b": b, "similarity": round(score, 2)})
    return sorted(pairs, key=lambda p: -p["similarity"])[:40]


def tokens_by_agent(skills):
    """Each agent pays only for the roots it loads."""
    out = {}
    for s in skills:
        for agent in sorted({AGENT_OF.get(c["root"], c["root"]) for c in s["copies"]}):
            out[agent] = out.get(agent, 0) + s["context_tokens"]
    return out


def same_name_hints(skills):
    """One name from two sources (say a local copy and a plugin) is a likely duplicate."""
    seen = {}
    for s in skills:
        seen.setdefault(s["name"], []).append(s["source"])
    return [{"a": n, "b": n, "similarity": 1.0, "sources": src} for n, src in seen.items() if len(src) > 1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", metavar="FILE", help="write the full roster as JSON ('-' for stdout)")
    ap.add_argument("--days", type=int, default=60, help="usage window in days (default 60)")
    ap.add_argument("--overlap", type=float, default=0.25, help="similarity threshold for overlap hints")
    args = ap.parse_args()

    entries = []
    for label, root in ROOTS:
        if root.is_dir():
            for d in sorted(root.iterdir()):
                if d.name.startswith(".") or not (d.is_dir() or d.is_symlink()):
                    continue
                if d.absolute() == SYNCED:
                    continue
                entries.append(inspect(label, d))
    if SYNCED.is_dir():
        for bucket in sorted(SYNCED.iterdir()):
            if bucket.is_dir() and not bucket.name.startswith("."):
                for d in sorted(bucket.iterdir()):
                    if d.is_dir() and not d.name.startswith("."):
                        entries.append(inspect("claude-synced", d, plugin=SYNCED_PREFIX))
    for plugin, d in plugin_dirs():
        if d.is_dir():
            entries.append(inspect("plugin", d, plugin=plugin))

    lock = load_lock()
    usage, log_files = scan_logs(args.days)

    # Group copies of the same skill name across roots.
    by_name = {}
    for e in entries:
        by_name.setdefault((e["plugin"] or "", e["name"]), []).append(e)
    skills = []
    for (plugin, name), copies in sorted(by_name.items()):
        hashes = {c.get("hash") for c in copies if c.get("hash")}
        keys = [f"{plugin}:{name}", name] if plugin else [name, copies[0]["dir_name"]]
        u = next((usage[k] for k in keys if k in usage), {})
        primary = next((c for c in copies if not c["is_symlink"]), copies[0])
        s = dict(primary)
        merged = []
        for c in copies:
            for prob in c["problems"]:
                tagged = prob if c is primary else f"{prob} ({c['root']} copy)"
                if tagged not in merged and prob not in merged:
                    merged.append(tagged)
        s["problems"] = merged
        s["copies"] = [{"root": c["root"], "path": c["path"], "symlink": c["is_symlink"]} for c in copies]
        if len(hashes) > 1:
            roots = ", ".join(c["root"] for c in copies)
            s["problems"] = s["problems"] + [f"copies differ ({roots})"]
        if s["plugin"]:
            s["source"] = "claude.ai sync" if s["plugin"] == SYNCED_PREFIX else f"plugin:{s['plugin']}"
        else:
            s["source"] = (lock.get(name) or {}).get("source") or "local"
        s["uses_total"] = u.get("total", 0)
        s["uses_window"] = u.get("window", 0)
        s["last_used"] = u.get("last_used")
        s["used_in"] = u.get("tools", [])
        skills.append(s)

    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "window_days": args.days,
        "log_files_scanned": log_files,
        "roots": [str(r) for _, r in ROOTS if r.is_dir()] + ([str(INSTALLED_PLUGINS)] if INSTALLED_PLUGINS.is_file() else []),
        "totals": {
            "skills": len(skills),
            "always_loaded_tokens": sum(s["context_tokens"] for s in skills),
            "tokens_by_agent": tokens_by_agent(skills),
            "never_used": sum(1 for s in skills if s["uses_total"] == 0),
            "idle_in_window": sum(1 for s in skills if s["uses_window"] == 0),
            "with_problems": sum(1 for s in skills if s["problems"]),
        },
        "skills": skills,
        "overlap_hints": same_name_hints(skills) + overlap_hints(skills, args.overlap),
    }

    if args.json:
        out = json.dumps(report, indent=2)
        if args.json == "-":
            print(out)
        else:
            Path(args.json).write_text(out)
            print(f"roster written to {args.json}", file=sys.stderr)

    if args.json != "-":
        t = report["totals"]
        per_agent = ", ".join(f"{a} ~{n}" for a, n in sorted(t["tokens_by_agent"].items()))
        print(f"{t['skills']} skills | always-loaded tokens: {per_agent} | "
              f"{t['never_used']} never used | {t['idle_in_window']} idle {args.days}d | "
              f"{t['with_problems']} with problems | {log_files} transcripts scanned\n")
        print(f"{'skill':34} {'uses':>5} {'last':>10} {'tokens':>6}  source / problems")
        for s in sorted(skills, key=lambda s: (s["uses_window"], s["uses_total"], -s["context_tokens"])):
            note = s["source"] + ("  ! " + "; ".join(s["problems"]) if s["problems"] else "")
            print(f"{s['name'][:34]:34} {s['uses_total']:>5} {s['last_used'] or '-':>10} {s['context_tokens']:>6}  {note}")


if __name__ == "__main__":
    main()
