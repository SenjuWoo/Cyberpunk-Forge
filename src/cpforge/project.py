"""Forge projects: manifest, scaffolding from templates, version bumps.

Project layout:
  cpforge.json   manifest (name, id, version, kinds, requirements, version files)
  game/          runtime files at their game-relative paths; this is what ships
  source/        anything that builds into game/ (C++ plugin, WolvenKit project)
  CHANGELOG.md   per-version notes (never packaged)
  dist/          packages, receipts, Nexus kit (git-ignored)
  .cpforge/      deploy receipts and backups (git-ignored)
"""
from __future__ import annotations

import datetime
import re
import shutil
from pathlib import Path

from . import __version__
from .util import TEMPLATES_DIR, ForgeError, load_json, save_json

MANIFEST = "cpforge.json"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
TEXT_SUFFIXES = {".reds", ".lua", ".yaml", ".yml", ".xl", ".xml", ".json", ".md", ".txt", ".cpp", ".hpp", ".h",
                 ".cmake", ".gitignore", ".tweak", ".csv", ".ini", ".bat", ".ps1"}


def make_id(name: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", name)
    ident = "".join(p[:1].upper() + p[1:] for p in parts)
    if not ident:
        raise ForgeError(f"cannot make a mod id from '{name}'", "use letters or digits in the name")
    if ident[0].isdigit():
        ident = "Mod" + ident
    return ident


def templates() -> dict[str, dict]:
    out = {}
    for d in sorted(TEMPLATES_DIR.iterdir()):
        meta = d / "template.json"
        if meta.is_file():
            info = load_json(meta)
            info["path"] = d
            out[d.name] = info
    return out


def find_project(start: str | Path | None) -> Path:
    p = Path(start or ".").resolve()
    for cand in [p, *p.parents]:
        if (cand / MANIFEST).is_file():
            return cand
    raise ForgeError(f"no {MANIFEST} in {p} or its parents", "run inside a project, pass --project, or create one: cpforge new")


def load_manifest(root: Path) -> dict:
    m = load_json(root / MANIFEST)
    for key in ("name", "id", "version"):
        if not m.get(key):
            raise ForgeError(f"{MANIFEST} is missing '{key}'")
    return m


def _render(text: str, values: dict) -> str:
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def new_project(name: str, kinds: list[str], out_dir: Path, author: str = "", description: str = "",
                force: bool = False) -> dict:
    available = templates()
    unknown = [k for k in kinds if k not in available]
    if unknown:
        raise ForgeError(f"unknown template(s): {', '.join(unknown)}", "available: " + ", ".join(available))
    ident = make_id(name)
    root = out_dir
    if root.exists() and any(root.iterdir()) and not force:
        raise ForgeError(f"{root} is not empty", "choose an empty folder or pass --force to add files to it")
    values = {"NAME": name, "ID": ident, "AUTHOR": author or "Unknown", "VERSION": "0.1.0",
              "YEAR": str(datetime.date.today().year), "DESCRIPTION": description or name,
              "ID_LOWER": ident.lower(), "FORGE_VERSION": __version__}
    written, skipped = [], []
    requires: dict[str, dict] = {}
    version_files: list[dict] = []
    for kind in kinds:
        tdir: Path = available[kind]["path"]
        for src in sorted(tdir.rglob("*")):
            if src.is_dir() or src.name == "template.json":
                continue
            relp = src.relative_to(tdir).as_posix().replace("__ID__", ident)
            dest = root / relp
            if dest.exists():
                skipped.append(relp)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix.lower() in TEXT_SUFFIXES or src.name in (".gitignore",):
                dest.write_text(_render(src.read_text(encoding="utf-8"), values), encoding="utf-8", newline="\n")
            else:
                shutil.copy2(src, dest)
            written.append(relp)
        for r in available[kind].get("requires", []):
            requires.setdefault(r["id"], r)
        for vf in available[kind].get("version_files", []):
            version_files.append({"path": vf["path"].replace("__ID__", ident), "pattern": vf["pattern"]})
    manifest_path = root / MANIFEST
    if manifest_path.is_file():
        manifest = load_json(manifest_path)
        manifest["kinds"] = sorted(set(manifest.get("kinds", [])) | set(kinds))
        have = {r["id"] for r in manifest.get("requires", [])}
        manifest.setdefault("requires", []).extend(r for r in requires.values() if r["id"] not in have)
        manifest.setdefault("version_files", []).extend(version_files)
    else:
        manifest = {"schema": 1, "name": name, "id": ident, "version": "0.1.0", "author": values["AUTHOR"],
                    "description": values["DESCRIPTION"], "kinds": kinds, "game_patch": "2.5",
                    "requires": list(requires.values()), "script_dependencies": [],
                    "version_files": version_files, "nexus": {"mod_id": None, "summary": ""},
                    "created_with": f"cpforge {__version__}"}
    save_json(manifest_path, manifest)
    for extra, body in ((".gitignore", "dist/\n.cpforge/\nsource/red4ext/build/\n*.log\n"),
                        ("CHANGELOG.md", f"# Changelog\n\n## 0.1.0 - {datetime.date.today().isoformat()}\n- First version.\n")):
        p = root / extra
        if not p.exists():
            p.write_text(body, encoding="utf-8", newline="\n")
            written.append(extra)
    return {"project": str(root), "id": ident, "kinds": manifest["kinds"], "written": written, "skipped": skipped,
            "next": ["cpforge check --project " + str(root), "cpforge package --project " + str(root)]}


def bump(root: Path, part: str) -> dict:
    m = load_manifest(root)
    old = m["version"]
    mm = SEMVER.match(old)
    if SEMVER.match(part):
        new = part
    elif mm and part in ("major", "minor", "patch"):
        a, b, c = (int(x) for x in mm.groups())
        new = {"major": f"{a + 1}.0.0", "minor": f"{a}.{b + 1}.0", "patch": f"{a}.{b}.{c + 1}"}[part]
    else:
        raise ForgeError(f"cannot bump '{old}' with '{part}'", "use major, minor, patch or an explicit X.Y.Z")
    changed = []
    # Keep the last good package before the version moves.
    kept = None
    dist = root / "dist"
    old_zip = dist / f"{m['id']}-{old}.zip"
    if old_zip.is_file():
        kg = dist / "known-good"
        kg.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_zip, kg / old_zip.name)
        kept = str(kg / old_zip.name)
    for vf in m.get("version_files", []):
        p = root / vf["path"]
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        rx = re.compile(vf["pattern"])
        hit = rx.search(text)
        if not hit or "v" not in rx.groupindex:
            continue
        text = text[: hit.start("v")] + new + text[hit.end("v"):]
        p.write_text(text, encoding="utf-8", newline="\n")
        changed.append(vf["path"])
    m["version"] = new
    save_json(root / MANIFEST, m)
    changed.append(MANIFEST)
    cl = root / "CHANGELOG.md"
    if cl.is_file():
        text = cl.read_text(encoding="utf-8")
        if f"## {new}" not in text:
            head = f"## {new} - {datetime.date.today().isoformat()}\n- \n\n"
            idx = text.find("## ")
            text = text[:idx] + head + text[idx:] if idx >= 0 else text + "\n" + head
            cl.write_text(text, encoding="utf-8", newline="\n")
            changed.append("CHANGELOG.md")
    return {"old": old, "new": new, "changed": changed, "known_good": kept,
            "next": "write the CHANGELOG.md entry, then cpforge check and cpforge package"}


def changelog_entries(root: Path) -> list[dict]:
    cl = root / "CHANGELOG.md"
    if not cl.is_file():
        return []
    out, cur = [], None
    for line in cl.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s+v?(\d+\.\d+\.\d+\S*)(?:\s*[-(]\s*(.*?)\)?)?\s*$", line)
        if m:
            cur = {"version": m.group(1), "date": (m.group(2) or "").strip(), "lines": []}
            out.append(cur)
        elif cur is not None and line.strip():
            cur["lines"].append(line.rstrip())
    return out
