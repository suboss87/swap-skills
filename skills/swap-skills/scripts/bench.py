#!/usr/bin/env python3
"""Bench skills instead of deleting them. Every move is logged and reversible.

  python3 bench.py out <skill-dir> [<skill-dir> ...]   # move to the bench
  python3 bench.py list                                # what is on the bench
  python3 bench.py back <name|session|--all>           # restore

The bench lives at ~/.swap-skills/bench/<session>/ with a manifest.json per session,
saved after every single move. Skills installed with `npx skills` also lose (and on
restore regain) their lock entry, so `npx skills update` does not quietly reinstall
a benched skill. Plugin skills are refused: run `claude plugin disable <plugin>`.
"""
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
BENCH = HOME / ".swap-skills" / "bench"
PLUGIN_CACHE = HOME / ".claude" / "plugins" / "cache"
LOCK = HOME / ".agents" / ".skill-lock.json"
LOCK_DIRS = (HOME / ".agents" / "skills", HOME / ".claude" / "skills")
SELF = Path(__file__).absolute()


def atomic_write(path, data):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


def read_lock():
    try:
        return json.loads(LOCK.read_text())
    except Exception:
        return None


def new_session():
    BENCH.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for n in range(1000):
        d = BENCH / (stamp if n == 0 else f"{stamp}-{n}")
        try:
            d.mkdir()
            return d
        except FileExistsError:
            continue
    raise RuntimeError("could not create a bench session")


def check(p):
    """Return an error string, or None when p is a single skill folder we may move."""
    if not (p.exists() or p.is_symlink()):
        return "not found"
    if PLUGIN_CACHE in p.parents or PLUGIN_CACHE in p.resolve().parents:
        return "plugin skill. Run: claude plugin disable <plugin>"
    if p.is_symlink() and not p.exists():
        return None  # broken symlink: benching it is the fix
    if not (p / "SKILL.md").is_file():
        return "no SKILL.md here, so this is not a single skill folder"
    return None


def out(paths):
    session = None
    manifest = None
    lock = read_lock()
    moved = 0
    for raw in paths:
        p = Path(os.path.abspath(os.path.expanduser(raw.rstrip("/"))))
        if p.name == "SKILL.md":
            p = p.parent
        err = check(p)
        if err:
            print(f"skip  {p}: {err}")
            continue
        if session is None:
            session = new_session()
            manifest = {"session": session.name, "items": []}
        tag = hashlib.sha1(str(p).encode()).hexdigest()[:8]
        target = session / f"{p.name}__{tag}"
        if target.exists() or target.is_symlink():
            print(f"skip  {p}: already on this bench session")
            continue
        item = {"name": p.name, "from": str(p), "to": str(target)}
        try:
            if p.is_symlink():
                item["symlink_to"] = os.readlink(p)
                target.write_text(item["symlink_to"])
                p.unlink()
            else:
                shutil.move(str(p), str(target))
        except OSError as e:
            print(f"fail  {p}: {e}")
            continue
        # Drop the lock entry once no copy is left in a lock-managed folder.
        if lock and p.name in (lock.get("skills") or {}) and not any(
            (d / p.name).exists() or (d / p.name).is_symlink() for d in LOCK_DIRS
        ):
            item["lock_entry"] = lock["skills"].pop(p.name)
            atomic_write(LOCK, lock)
        manifest["items"].append(item)
        atomic_write(session / "manifest.json", manifest)
        moved += 1
        print(f"bench {p}")
    if moved:
        print(f"\n{moved} benched. Undo: python3 {SELF} back {session.name}")
    elif session is not None:
        shutil.rmtree(session, ignore_errors=True)


def sessions():
    if not BENCH.is_dir():
        return []
    found = []
    for d in sorted(BENCH.iterdir()):
        m = d / "manifest.json"
        if m.is_file():
            try:
                found.append((d, json.loads(m.read_text())))
            except ValueError:
                print(f"warn  unreadable manifest: {m}")
    return found


def list_bench():
    rows = [(m["session"], it) for _, m in sessions() for it in m["items"]]
    for s, it in rows:
        print(f"{s}  {it['name']:32}  from {it['from']}")
    if not rows:
        print("bench is empty")


def back(selector):
    lock = read_lock()
    restored = 0
    for d, m in sessions():
        keep = []
        for it in m["items"]:
            if selector not in ("--all", m["session"], it["name"]):
                keep.append(it)
                continue
            src, dst = Path(it["to"]), Path(it["from"])
            if dst.exists() or dst.is_symlink():
                print(f"skip  {it['name']}: {dst} exists again")
                keep.append(it)
                continue
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if "symlink_to" in it:
                    dst.symlink_to(it["symlink_to"])
                    src.unlink()
                else:
                    shutil.move(str(src), str(dst))
            except OSError as e:
                print(f"fail  {it['name']}: {e}")
                keep.append(it)
                continue
            if "lock_entry" in it and lock is not None:
                lock.setdefault("skills", {})[it["name"]] = it["lock_entry"]
                atomic_write(LOCK, lock)
            restored += 1
            print(f"back  {dst}")
        if keep:
            m["items"] = keep
            atomic_write(d / "manifest.json", m)
        else:
            shutil.rmtree(d, ignore_errors=True)
    print(f"{restored} restored")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "out" and rest:
        out(rest)
    elif cmd == "list":
        list_bench()
    elif cmd == "back" and rest:
        back(rest[0])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
