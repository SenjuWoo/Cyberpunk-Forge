"""Nexus Mods page kit from the manifest and CHANGELOG.md. Writes files; never uploads."""
from __future__ import annotations

import re
from pathlib import Path

from .project import changelog_entries, load_manifest
from .util import KNOWLEDGE_DIR, load_json

INSTALL_HINT = {
    "r6/scripts": "redscript",
    "r6/tweaks": "TweakXL",
    "bin/x64/plugins/cyber_engine_tweaks/mods": "Cyber Engine Tweaks",
    "archive/pc/mod": "archive",
    "red4ext/plugins": "RED4ext",
    "r6/input": "Input Loader",
    "r6/audioware": "Audioware",
    "mods/": "REDmod",
}
PRIVATE = re.compile(r"[A-Za-z]:\\|\\Users\\|/Users/|/home/")


def _requirements(m: dict) -> list[dict]:
    reg = {f["id"]: f for f in load_json(KNOWLEDGE_DIR / "frameworks.json")["frameworks"]}
    out = []
    for r in m.get("requires", []):
        fw = reg.get(r["id"], {})
        out.append({"name": fw.get("name", r["id"]), "url": fw.get("nexus") or fw.get("repo") or "",
                    "min": r.get("min", ""), "optional": bool(r.get("optional"))})
    return out


def kit(root: Path) -> dict:
    m = load_manifest(root)
    entries = changelog_entries(root)
    reqs = _requirements(m)
    out = root / "dist" / "nexus" / m["version"]
    out.mkdir(parents=True, exist_ok=True)
    surfaces = sorted({v for k, v in INSTALL_HINT.items() if (root / "game" / k).exists()})
    summary = m.get("nexus", {}).get("summary") or m.get("description", m["name"])
    current = next((e for e in entries if e["version"] == m["version"]), None)
    lines = [f"[size=5][b]{m['name']}[/b][/size]", "", summary, ""]
    if current and current["lines"]:
        lines += [f"[size=4][b]What's new in {m['version']}[/b][/size]", "[list]"]
        lines += ["[*]" + re.sub(r"^[-*]\s*", "", ln) for ln in current["lines"] if ln.strip().startswith(("-", "*"))]
        lines += ["[/list]", ""]
    lines += ["[size=4][b]Requirements[/b][/size]", "[list]"]
    for r in reqs:
        label = r["name"] + (f" {r['min']}+" if r["min"] else "") + (" (optional)" if r["optional"] else "")
        lines.append(f"[*][url={r['url']}]{label}[/url]" if r["url"] else f"[*]{label}")
    lines += ["[/list]", "", "[size=4][b]Installation[/b][/size]",
              "Install with Vortex or Mod Organizer 2, or extract the archive into the game folder "
              "(the folder that contains bin and r6).", ""]
    if m.get("game_patch"):
        lines.append(f"Built for Cyberpunk 2077 {m['game_patch']}.")
    description = "\n".join(lines).rstrip() + "\n"
    changelog = "\n\n".join(f"{e['version']}\n" + "\n".join(e["lines"]) for e in entries) + "\n"
    file_desc = f"{m['name']} {m['version']}" + (f" - {current['lines'][0].lstrip('-* ').strip()}" if current and current["lines"] else "")
    files = {"description.bbcode": description, "changelog.txt": changelog, "file-description.txt": file_desc + "\n",
             "summary.txt": summary[:350] + "\n"}
    leaks = []
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8", newline="\n")
        if PRIVATE.search(text):
            leaks.append(name)
    return {"folder": str(out), "files": sorted(files), "requirements": reqs, "surfaces": surfaces,
            "private_path_in": leaks, "changelog_versions": [e["version"] for e in entries],
            "note": "Review before pasting. The forge never uploads; publishing is your step."}
