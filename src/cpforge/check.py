"""Validate a project against the installed game. Every check reports what it covered and what it skipped."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from . import index as idxmod
from . import redscript
from .archive import read_archive
from .game import find_game, find_tool
from .package import ALLOWED_ROOTS, scan_secrets
from .project import SEMVER, load_manifest
from .tweakdb import TweakDB, installed_yaml_records, parse_yaml, references, yaml_records
from .util import KNOWLEDGE_DIR, ForgeError, iter_files, load_json, rel


class Report:
    def __init__(self):
        self.errors, self.warnings, self.gaps, self.checked = [], [], [], []

    def add(self, level, code, msg, file=None, line=None, **kw):
        item = {"code": code, "message": msg}
        if file:
            item["file"] = file
        if line:
            item["line"] = line
        item.update(kw)
        (self.errors if level == "error" else self.warnings).append(item)

    def gap(self, what, why):
        self.gaps.append({"check": what, "why": why})

    def done(self, what):
        if what not in self.checked:
            self.checked.append(what)


def _lua_check(files: list[Path], rep: Report, root: Path):
    tool = find_tool("luajit")
    events = set(load_json(KNOWLEDGE_DIR / "facts.json")["facts"]["cet.events"]["value"])
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"registerForEvent\s*\(\s*['\"](\w+)['\"]", text):
            if m.group(1) not in events:
                rep.add("error", "CET-EVENT", f"unknown CET event '{m.group(1)}' (known: {', '.join(sorted(events))})",
                        rel(f, root), text.count("\n", 0, m.start()) + 1)
    rep.done("cet events")
    if not tool:
        rep.gap("lua syntax", "no luajit/luac on PATH (set CPFORGE_LUA to one)")
        return
    for f in files:
        name = Path(tool).name.lower()
        if "luajit" in name:
            with tempfile.TemporaryDirectory() as td:
                cmd = [tool, "-b", str(f), str(Path(td) / "out.bc")]
                p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        else:
            p = subprocess.run([tool, "-p", str(f)], capture_output=True, text=True, errors="replace")
        if p.returncode != 0:
            rep.add("error", "LUA-SYNTAX", (p.stderr or p.stdout).strip()[:300], rel(f, root))
    rep.done("lua syntax")


def _tweak_check(files: list[Path], rep: Report, root: Path, game: Path | None, idx: dict | None):
    tdb = TweakDB(game) if game else None
    known_types = set(idx["record_types"].values()) if idx else set()
    project_records: dict[str, str] = {}
    parsed = []
    for f in files:
        try:
            recs = yaml_records(f)
            parsed.append((f, recs, parse_yaml(f)))
            for name in recs["records"]:
                project_records[name] = rel(f, root)
        except ForgeError as e:
            rep.add("error", "TWEAK-YAML", str(e), rel(f, root))
        except Exception as e:  # PyYAML errors carry line info in str(e)
            rep.add("error", "TWEAK-YAML", f"YAML does not parse: {str(e)[:300]}", rel(f, root))
    rep.done("tweak yaml syntax")
    if not tdb:
        rep.gap("tweak references", "game not found, cannot check record names")
        return
    installed = installed_yaml_records(game)
    packages = {n.split(".")[0] for n in (idx["tweak_records"] if idx else {})}

    def exists(name: str) -> bool:
        return name in project_records or tdb.exists(name) or name in installed

    for f, recs, doc in parsed:
        fr = rel(f, root)
        for name, r in recs["records"].items():
            t = r["type"]
            if t and known_types:
                bare = re.sub(r"^gamedata|_Record$", "", str(t))
                if bare not in known_types:
                    rep.add("error", "TWEAK-TYPE", f"{name}: unknown $type '{t}'", fr)
            if r["base"] and not exists(str(r["base"])):
                rep.add("error", "TWEAK-BASE", f"{name}: $base '{r['base']}' is not in TweakDB or any installed tweak", fr)
            if not t and not r["base"] and not exists(name) and not r["instances"]:
                rep.add("error", "TWEAK-NEW-NO-TYPE", f"{name}: new record needs $type or $base", fr)
            for ref in references(doc.get(name)):
                if ref.split(".")[0] in packages and not exists(ref):
                    rep.add("warning", "TWEAK-REF", f"{name}: '{ref}' looks like a record name but does not exist", fr)
        for flat in recs["flats"]:
            owner = flat.rsplit(".", 1)[0]
            if "." in flat and not exists(owner) and owner.split(".")[0] in packages:
                rep.add("warning", "TWEAK-FLAT", f"flat '{flat}': record '{owner}' not found", fr)
    rep.done("tweak references (" + ", ".join(tdb.sources) + ")")


def _xl_check(files: list[Path], rep: Report, root: Path):
    for f in files:
        try:
            doc = parse_yaml(f) or {}
        except Exception as e:
            rep.add("error", "XL-YAML", f"does not parse: {str(e)[:300]}", rel(f, root))
            continue
        arc_path = f.with_name(f.name[: -len(".xl")])
        paths = []
        for p in doc.get("factories", []) or []:
            paths.append(str(p))
        for lang, p in ((doc.get("localization") or {}).get("onscreens") or {}).items():
            paths.append(str(p))
        if not arc_path.is_file():
            rep.gap(f"archive contents for {rel(f, root)}", "the .archive is not built yet (pack it with WolvenKit)")
            continue
        arc = read_archive(arc_path)
        for p in paths:
            if not arc.contains(p):
                rep.add("error", "XL-MISSING", f"'{p}' is not inside {arc_path.name}", rel(f, root))
    if files:
        rep.done("archivexl files")


def _xml_check(files: list[Path], rep: Report, root: Path):
    for f in files:
        try:
            tree = ET.parse(f)
        except ET.ParseError as e:
            rep.add("error", "INPUT-XML", f"not well-formed XML: {e}", rel(f, root))
            continue
        r = tree.getroot()
        if r.tag != "bindings":
            rep.add("error", "INPUT-ROOT", f"root element is <{r.tag}>, Input Loader expects <bindings>", rel(f, root))
        for ctx in r.iter("context"):
            if not ctx.get("name"):
                rep.add("error", "INPUT-CONTEXT", "<context> without name", rel(f, root))
    if files:
        rep.done("input xml")


def check_project(root: Path, game_arg: str | None = None, compile_scripts: bool = False) -> dict:
    rep = Report()
    m = load_manifest(root)
    if not SEMVER.match(m["version"]):
        rep.add("error", "MANIFEST-VERSION", f"version '{m['version']}' is not semantic (X.Y.Z)", "cpforge.json")
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", m["id"]):
        rep.add("error", "MANIFEST-ID", "id must be letters, digits, underscore", "cpforge.json")
    rep.done("manifest")
    game_dir = root / "game"
    files = list(iter_files(game_dir)) if game_dir.is_dir() else []
    if not files:
        rep.add("error", "LAYOUT-EMPTY", "no files under game/")
    for f in files:
        r = f.relative_to(game_dir).as_posix()
        if not r.startswith(ALLOWED_ROOTS):
            rep.add("warning", "LAYOUT-ROOT", "file outside the usual game folders", "game/" + r)
        for s in scan_secrets(r, f.read_bytes() if f.stat().st_size < (4 << 20) else b""):
            rep.add("error", "SECRET", f"looks like a {s['kind']} ({s['match']})", "game/" + r, s["line"])
    for f in iter_files(root / "source"):
        if f.stat().st_size < (4 << 20) and "build" not in f.parts:
            for s in scan_secrets(f.name, f.read_bytes()):
                rep.add("warning", "SECRET-SOURCE", f"looks like a {s['kind']} in source/", rel(f, root), s["line"])
    rep.done("layout and secrets")
    for vf in m.get("version_files", []):
        p = root / vf["path"]
        if p.is_file():
            hit = re.search(vf["pattern"], p.read_text(encoding="utf-8", errors="replace"))
            if hit and "v" in hit.groupdict() and hit.group("v") != m["version"]:
                rep.add("error", "VERSION-MISMATCH", f"{vf['path']} says {hit.group('v')}, cpforge.json says {m['version']}")
    rep.done("version mirrors")

    game = None
    try:
        game, _, _ = find_game(game_arg)
    except ForgeError as e:
        rep.gap("installed game", str(e))
    idx = idxmod.load(game, required=False) if game else None
    if game and not idx:
        rep.gap("hook targets and record types", "no index for this game version: run cpforge index")

    reds = [f for f in files if f.suffix == ".reds"]
    if reds:
        for fnd in redscript.static_check(reds, idx):
            fnd["file"] = rel(Path(fnd["file"]), root)
            (rep.errors if fnd.pop("level") == "error" else rep.warnings).append(fnd)
        rep.done("redscript static" + (" + hook targets" if idx else ""))
        if compile_scripts:
            if not game or os.name != "nt":
                rep.gap("redscript compile", "needs Windows and the installed game")
            else:
                dirs = sorted({f.parent for f in reds if "r6/scripts" in f.as_posix()})
                top = [d for d in dirs if not any(o != d and o in d.parents for o in dirs)]
                res = redscript.compile_scripts(game, top, m["id"], m.get("script_dependencies") or [])
                for d in res["errors"]:
                    rep.add("error", "RS-COMPILE", d["message"] + (" " + " | ".join(d["detail"][:3]) if d["detail"] else ""),
                            d.get("file"), d.get("line"), compiler_code=d.get("code"))
                if res.get("missing_dependencies"):
                    rep.add("error", "RS-DEPS", "script dependencies not installed: " + ", ".join(res["missing_dependencies"]))
                if res.get("timed_out") or (res.get("exit_code") not in (0, None) and not res["errors"]):
                    rep.add("error", "RS-COMPILER", res.get("hint") or "compiler failed without diagnostics",
                            log_tail=res.get("log_tail"))
                rep.done("redscript compile (scc.exe)")
        else:
            rep.gap("redscript compile", "not requested (add --compile)")
    lua = [f for f in files if f.suffix == ".lua"]
    if lua:
        _lua_check(lua, rep, root)
    yamls = [f for f in files if f.suffix in (".yaml", ".yml") and "r6/tweaks" in f.as_posix()]
    if yamls:
        _tweak_check(yamls, rep, root, game, idx)
    if any(f.suffix == ".tweak" for f in files):
        rep.gap("RED .tweak files", "syntax not checked by the forge yet; TweakXL reports errors in its log")
    _xl_check([f for f in files if f.name.endswith(".archive.xl")], rep, root)
    _xml_check([f for f in files if f.suffix == ".xml" and "r6/input" in f.as_posix()], rep, root)
    for info in [f for f in files if f.name == "info.json" and "/mods/" in "/" + f.relative_to(game_dir).as_posix()]:
        data = load_json(info)
        for k in ("name", "version"):
            if not data.get(k):
                rep.add("error", "REDMOD-INFO", f"info.json needs '{k}'", rel(info, root))
        rep.done("redmod info.json")
    for y in [f for f in files if f.suffix in (".yaml", ".yml") and "r6/audioware" in f.as_posix()]:
        try:
            doc = parse_yaml(y) or {}
        except Exception as e:
            rep.add("error", "AUDIOWARE-YAML", f"does not parse: {str(e)[:200]}", rel(y, root))
            continue
        for key, entry in (doc.get("sfx") or {}).items():
            fname = entry.get("file") if isinstance(entry, dict) else None
            if fname and not (y.parent / fname).is_file():
                rep.add("warning", "AUDIOWARE-FILE", f"sfx '{key}': file '{fname}' not found next to the manifest", rel(y, root))
        rep.done("audioware manifests")
    if "red4ext" in m.get("kinds", []):
        dll = game_dir / "red4ext" / "plugins" / m["id"] / f"{m['id']}.dll"
        if not dll.is_file():
            rep.gap("red4ext plugin", "DLL not built yet: cpforge build")
    return {"project": m["id"], "version": m["version"], "ok": not rep.errors, "errors": rep.errors,
            "warnings": rep.warnings, "gaps": rep.gaps, "checked": rep.checked,
            "evidence": "tool-validated (static)" + (" + compile" if compile_scripts else "") + "; not a runtime test"}
