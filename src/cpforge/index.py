"""Local API and TweakDB index built from what is installed.

Sources (all read-only, all on the user's machine):
- tools/redmod/scripts/**/*.script  vanilla script source (REDmod DLC)
- tools/redmod/metadata.json        native RTTI dump (REDmod DLC)
- tools/redmod/tweaks/**/*.tweak    vanilla TweakDB source (REDmod DLC)
- r6/scripts/**/*.reds, red4ext/plugins/**/*.reds  installed mods and libraries
The index lives under the forge home, keyed by game version. Game files are
never copied into a project or into this repository.
"""
from __future__ import annotations

import gzip
import json
import re
import time
from pathlib import Path

from . import __version__, tweaksrc
from .game import game_version
from .util import ForgeError, home_dir, iter_files, read_text, record_type_key, rel

# 3: .tweak records parsed by tweaksrc (base-less and dotted records included).
INDEX_SCHEMA = 3
MODS = r"(?:(?:public|private|protected|final|static|native|abstract|importonly|import|const|cb|exec|quest|persistent|editable|instanceeditable|inline|override|unsafe|optional|out|event|latent|replicated|saved|rep|default|edit|inlined|safe|noexport|export|virtual|callback|mutable)\s+)*"

# CDPR .script syntax
S_TYPE = re.compile(r"^\s*" + MODS + r"(class|struct|enum)\s+(\w+)(?:\s+extends\s+(\w+))?")
S_FUNC = re.compile(r"^\s*(?P<mods>" + MODS + r")(?P<kw>function|event)\s+(?P<name>\w+)\s*\(")
S_FIELD = re.compile(r"^\s*(" + MODS + r")var\s+(\w+)\s*:\s*([^;=]+)")
# redscript .reds syntax
R_TYPE = re.compile(r"^\s*" + MODS + r"(class|struct|enum)\s+(\w+)(?:\s+extends\s+(\w+))?")
R_FUNC = re.compile(r"^\s*(?P<mods>" + MODS + r")(?P<kw>func)\s+(?P<name>\w+)\s*\(")
R_FIELD = re.compile(r"^\s*(" + MODS + r")let\s+(\w+)\s*:\s*([^;=]+)")
ANNOT = re.compile(r"^\s*@(wrapMethod|replaceMethod|addMethod|addField|replaceGlobal)\s*\(\s*(\w*)\s*\)")
ENUM_VAL = re.compile(r"^\s*(\w+)\s*(?:=\s*(-?\w+))?\s*,?\s*(?://.*)?$")


def index_dir(game_root: Path) -> Path:
    ver = game_version(game_root).get("exe_file_version") or "unknown"
    return home_dir() / "index" / ver


def _signature(lines: list[str], i: int, syntax: str) -> tuple[str, str]:
    """Join a declaration until its closing parenthesis; return (params, return type)."""
    text = lines[i]
    j = i
    while text.count("(") > text.count(")") and j < i + 8 and j + 1 < len(lines):
        j += 1
        text += " " + lines[j].strip()
    m = re.search(r"\((.*?)\)\s*(.*)$", text)
    if not m:
        return "", ""
    params = " ".join(m.group(1).split())
    rest = m.group(2)
    ret = ""
    if syntax == "script":
        r = re.match(r":\s*([\w<>\[\],:\s]+?)\s*(?:\{|;|$)", rest)
    else:
        r = re.match(r"->\s*([\w<>\[\],:\s]+?)\s*(?:\{|;|$)", rest)
    if r:
        ret = " ".join(r.group(1).split())
    return params, ret


def parse_source(text: str, syntax: str, origin: str, file: str, out: dict) -> None:
    """Add classes, functions, fields, enums and hook annotations from one file."""
    type_re, func_re, field_re = (S_TYPE, S_FUNC, S_FIELD) if syntax == "script" else (R_TYPE, R_FUNC, R_FIELD)
    lines = text.splitlines()
    depth = 0
    stack: list[tuple[str, str, int]] = []  # (kind, name, depth at which members live)
    pending: tuple[str, str] | None = None
    annot: tuple[str, str] | None = None
    for i, line in enumerate(lines):
        code = line.split("//", 1)[0]
        cur = stack[-1] if stack and stack[-1][2] == depth else None
        a = ANNOT.match(code)
        if a:
            annot = (a.group(1), a.group(2))
        t = type_re.match(code) if not cur or cur[0] != "enum" else None
        if t and depth == 0:
            kind, name, parent = t.group(1), t.group(2), t.group(3)
            if kind == "enum":
                out["enums"].setdefault(name, {"values": {}, "origin": origin, "file": file, "line": i + 1})
            else:
                c = out["classes"].setdefault(name, {"kind": kind, "parent": parent, "origin": origin, "file": file,
                                                     "line": i + 1, "funcs": [], "fields": []})
                if parent and not c.get("parent"):
                    c["parent"] = parent
            pending = (kind, name)
        elif cur and cur[0] == "enum":
            ev = ENUM_VAL.match(code)
            if ev and ev.group(1) not in ("{", "}"):
                out["enums"][cur[1]]["values"][ev.group(1)] = ev.group(2)
        else:
            f = func_re.match(code)
            fld = field_re.match(code) if not f else None
            owner = cur[1] if cur and cur[0] != "enum" else None
            if f:
                params, ret = _signature(lines, i, syntax)
                fmods = " ".join(f.group("mods").split())
                is_event = f.group("kw") == "event" or "cb" in fmods.split()
                entry = {"name": f.group("name"), "params": params, "ret": ret or ("Bool" if is_event else ""),
                         "mods": fmods, "event": is_event, "origin": origin, "file": file, "line": i + 1}
                if annot and annot[0] in ("wrapMethod", "replaceMethod", "addMethod", "replaceGlobal"):
                    out["hooks"].append({"kind": annot[0], "class": annot[1], "member": f.group("name"), "origin": origin,
                                         "file": file, "line": i + 1, "params": params})
                    if annot[0] == "addMethod" and annot[1]:
                        out["classes"].setdefault(annot[1], {"kind": "class", "parent": None, "origin": "native?",
                                                             "file": "", "line": 0, "funcs": [], "fields": []})
                        out["classes"][annot[1]]["funcs"].append(entry)
                elif owner and depth == cur[2]:
                    out["classes"][owner]["funcs"].append(entry)
                elif depth == 0:
                    out["globals"].append(entry)
                annot = None
            elif fld:
                entry = {"name": fld.group(2), "type": " ".join(fld.group(3).split()), "mods": " ".join(fld.group(1).split()),
                         "origin": origin, "file": file, "line": i + 1}
                if annot and annot[0] == "addField" and annot[1]:
                    out["hooks"].append({"kind": "addField", "class": annot[1], "member": fld.group(2), "origin": origin,
                                         "file": file, "line": i + 1, "params": entry["type"]})
                    out["classes"].setdefault(annot[1], {"kind": "class", "parent": None, "origin": "native?",
                                                         "file": "", "line": 0, "funcs": [], "fields": []})
                    out["classes"][annot[1]]["fields"].append(entry)
                elif owner and depth == cur[2]:
                    out["classes"][owner]["fields"].append(entry)
                annot = None
        opens, closes = code.count("{"), code.count("}")
        if opens and pending:
            depth += 1
            stack.append((pending[0], pending[1], depth))
            pending = None
            opens -= 1
        depth += opens
        for _ in range(closes):
            if stack and stack[-1][2] == depth:
                stack.pop()
            depth = max(0, depth - 1)
        if depth == 0 and pending and code.strip().endswith(";"):
            pending = None


def _merge_native(meta: dict, out: dict) -> None:
    for c in meta.get("classes", []):
        name = c.get("name")
        if not name:
            continue
        entry = out["classes"].setdefault(name, {"kind": "class", "parent": c.get("parent"), "origin": "native",
                                                 "file": "", "line": 0, "funcs": [], "fields": []})
        if not entry.get("parent") and c.get("parent"):
            entry["parent"] = c["parent"]
        have = {f["name"] for f in entry["funcs"]}
        for fn in c.get("functions", []) + c.get("static_functions", []):
            if fn.get("name") and fn["name"] not in have:
                entry["funcs"].append({"name": fn["name"], "params": "?", "ret": "?", "mods": "native",
                                       "origin": "native", "file": "", "line": 0})
        have_f = {f["name"] for f in entry["fields"]}
        for p in c.get("properties", []):
            if p.get("name") and p["name"] not in have_f:
                entry["fields"].append({"name": p["name"], "type": p.get("type", "?"), "mods": "native",
                                        "origin": "native", "file": "", "line": 0})
    for e in meta.get("enums", []):
        if e.get("name"):
            out["enums"].setdefault(e["name"], {"values": {k: str(v) for k, v in (e.get("options") or {}).items()},
                                                "origin": "native", "file": "", "line": 0})
    have_g = {g["name"] for g in out["globals"]}
    for g in meta.get("global_functions", []):
        if g.get("name") and g["name"] not in have_g:
            out["globals"].append({"name": g["name"], "params": "?", "ret": "?", "mods": "native", "origin": "native",
                                   "file": "", "line": 0})


def parse_tweak_source(text: str, file: str, records: dict) -> None:
    """Records from one .tweak file, including base-less ones (`baseState {`) and dotted names."""
    parsed = tweaksrc.parse(text)
    for name, r in tweaksrc.full_names(parsed).items():
        records.setdefault(name, {"base": r["base"], "file": file, "line": r["line"]})


def build(game_root: Path, include_mods: bool = True) -> dict:
    start = time.time()
    out = {"classes": {}, "enums": {}, "globals": [], "hooks": []}
    counts = {"script_files": 0, "reds_files": 0, "tweak_files": 0}
    redmod = game_root / "tools/redmod"
    for f in iter_files(redmod / "scripts", (".script",)):
        parse_source(read_text(f), "script", "vanilla", rel(f, game_root), out)
        counts["script_files"] += 1
    meta = redmod / "metadata.json"
    if meta.is_file():
        _merge_native(json.loads(read_text(meta)), out)
    if include_mods:
        for base in (game_root / "r6/scripts", game_root / "red4ext/plugins"):
            for f in iter_files(base, (".reds",)):
                r = rel(f, game_root)
                parts = r.split("/")
                origin = "mod:" + (parts[2] if len(parts) > 3 else parts[-1])
                parse_source(read_text(f), "reds", origin, r, out)
                counts["reds_files"] += 1
    records: dict = {}
    for f in iter_files(redmod / "tweaks", (".tweak",)):
        parse_tweak_source(read_text(f), rel(f, game_root), records)
        counts["tweak_files"] += 1
    record_types = {}
    for name in out["classes"]:
        if name.endswith("_Record"):
            # Script name (Clothing_Record) and native name (gamedataClothing_Record) share a key; store the bare name.
            bare = name[: -len("_Record")]
            bare = bare[len("gamedata"):] if bare.startswith("gamedata") else bare
            record_types[str(record_type_key(name))] = bare
    index = {"schema": INDEX_SCHEMA, "forge_version": __version__, "game": str(game_root),
             "game_version": game_version(game_root), "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "counts": dict(counts, classes=len(out["classes"]), enums=len(out["enums"]),
                            globals=len(out["globals"]), hooks=len(out["hooks"]), tweak_records=len(records)),
             "api": out, "tweak_records": records, "record_types": record_types,
             "seconds": round(time.time() - start, 1)}
    d = index_dir(game_root)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "index.json.gz.tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(index, f)
    tmp.replace(d / "index.json.gz")
    return index


_CACHE: dict[str, dict] = {}


def load(game_root: Path, required: bool = True) -> dict | None:
    p = index_dir(game_root) / "index.json.gz"
    key = str(p)
    if key in _CACHE:
        return _CACHE[key]
    if not p.is_file():
        if required:
            raise ForgeError("no API index for this game version", "run: cpforge index")
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        idx = json.load(f)
    if idx.get("schema") != INDEX_SCHEMA:
        if required:
            raise ForgeError("API index was built by an older forge", "run: cpforge index")
        return None
    _CACHE[key] = idx
    return idx


def class_chain(idx: dict, name: str) -> list[str]:
    chain, seen = [], set()
    classes = idx["api"]["classes"]
    while name and name in classes and name not in seen:
        chain.append(name)
        seen.add(name)
        name = classes[name].get("parent")
    return chain


def find_member(idx: dict, cls: str, member: str) -> dict | None:
    """Find a function or field on a class or its parents."""
    classes = idx["api"]["classes"]
    for c in class_chain(idx, cls):
        for f in classes[c]["funcs"] + classes[c]["fields"]:
            if f["name"] == member:
                return dict(f, owner=c)
    return None


def search(idx: dict, query: str, kind: str = "any", limit: int = 40) -> list[dict]:
    words = query.lower().split() or [""]
    q = "".join(words)
    exact, prefix, sub = [], [], []

    def bucket(name: str, item: dict):
        n = name.lower()
        if n == q:
            exact.append(item)
        elif n.startswith(q) or (len(words) > 1 and n.startswith(words[0]) and all(w in n for w in words)):
            prefix.append(item)
        elif all(w in n for w in words):
            sub.append(item)

    api = idx["api"]
    if kind in ("any", "class"):
        for name, c in api["classes"].items():
            bucket(name, {"kind": c["kind"], "name": name, "parent": c.get("parent"), "origin": c["origin"],
                          "where": f"{c['file']}:{c['line']}" if c["file"] else c["origin"]})
    if kind in ("any", "enum"):
        for name, e in api["enums"].items():
            bucket(name, {"kind": "enum", "name": name, "values": list(e["values"])[:12], "origin": e["origin"]})
    if kind in ("any", "func"):
        for cname, c in api["classes"].items():
            for f in c["funcs"]:
                bucket(f["name"], {"kind": "func", "name": f"{cname}.{f['name']}", "params": f["params"], "ret": f["ret"],
                                   "mods": f["mods"], "origin": f["origin"],
                                   "where": f"{f['file']}:{f['line']}" if f["file"] else f["origin"]})
        for f in api["globals"]:
            bucket(f["name"], {"kind": "global", "name": f["name"], "params": f["params"], "ret": f["ret"],
                               "origin": f["origin"], "where": f"{f['file']}:{f['line']}" if f["file"] else f["origin"]})
    if kind in ("any", "field"):
        for cname, c in api["classes"].items():
            for f in c["fields"]:
                bucket(f["name"], {"kind": "field", "name": f"{cname}.{f['name']}", "type": f["type"], "origin": f["origin"]})
    return (exact + prefix + sub)[:limit]


# --- Patch diff between two stored indexes --------------------------------------

GAME_ORIGINS = ("vanilla", "native", "native?")


def stored_versions() -> list[dict]:
    """Every index kept under the forge home (one per game exe version)."""
    out = []
    for p in sorted((home_dir() / "index").glob("*/index.json.gz")):
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                head = json.load(f)
        except (OSError, ValueError):
            continue
        gv = head.get("game_version") or {}
        out.append({"version": p.parent.name, "patch": gv.get("patch"), "schema": head.get("schema"),
                    "built": head.get("built"), "counts": head.get("counts"), "path": str(p)})
    return out


def load_version(spec: str) -> dict:
    """Load a stored index by exe file version (3.0.88.46235) or patch label (2.5)."""
    versions = stored_versions()
    hit = [v for v in versions if spec in (v["version"], v["patch"])]
    if not hit:
        have = ", ".join(f"{v['version']} ({v['patch'] or '?'})" for v in versions) or "none"
        raise ForgeError(f"no stored index for '{spec}' (stored: {have})",
                         "run cpforge index on each game version you want to compare; old indexes are kept")
    v = hit[-1]
    with gzip.open(v["path"], "rt", encoding="utf-8") as f:
        idx = json.load(f)
    if not isinstance(idx.get("schema"), int) or idx["schema"] < 2:
        raise ForgeError(f"index for {spec} is too old to compare", "rebuild it with cpforge index on that version")
    return idx


def _game_api(idx: dict) -> dict:
    """Classes, members, enums and globals that come from the game itself, not from mods."""
    classes = {}
    for name, c in idx["api"]["classes"].items():
        funcs = {f["name"]: f for f in c["funcs"] if f["origin"] in GAME_ORIGINS}
        fields = {f["name"]: f for f in c["fields"] if f["origin"] in GAME_ORIGINS}
        if c["origin"] in GAME_ORIGINS or funcs or fields:
            classes[name] = {"parent": c.get("parent"), "funcs": funcs, "fields": fields}
    enums = {n: e for n, e in idx["api"]["enums"].items() if e["origin"] in GAME_ORIGINS}
    globals_ = {g["name"]: g for g in idx["api"]["globals"] if g["origin"] in GAME_ORIGINS}
    return {"classes": classes, "enums": enums, "globals": globals_}


def _sig(f: dict) -> str | None:
    if f.get("params") in (None, "?") and f.get("ret") in (None, "?"):
        return None  # native entries carry no signature
    return f"({f.get('params', '')}) -> {f.get('ret', '')}"


def diff(old: dict, new: dict, limit: int = 200) -> dict:
    """What a patch removed, added or changed in the game's script API and TweakDB."""
    a, b = _game_api(old), _game_api(new)
    removed_classes = sorted(set(a["classes"]) - set(b["classes"]))
    added_classes = sorted(set(b["classes"]) - set(a["classes"]))
    removed_members, added_members, changed, reparented = [], [], [], []
    for name in sorted(set(a["classes"]) & set(b["classes"])):
        ca, cb = a["classes"][name], b["classes"][name]
        if ca["parent"] and cb["parent"] and ca["parent"] != cb["parent"]:
            reparented.append({"class": name, "old": ca["parent"], "new": cb["parent"]})
        for kind in ("funcs", "fields"):
            for m in sorted(set(ca[kind]) - set(cb[kind])):
                removed_members.append({"class": name, "member": m, "kind": kind[:-1]})
            for m in sorted(set(cb[kind]) - set(ca[kind])):
                added_members.append({"class": name, "member": m, "kind": kind[:-1]})
        for m in sorted(set(ca["funcs"]) & set(cb["funcs"])):
            sa, sb = _sig(ca["funcs"][m]), _sig(cb["funcs"][m])
            if sa and sb and sa != sb:
                changed.append({"class": name, "member": m, "old": sa, "new": sb})
    removed_values = []
    for name in sorted(set(a["enums"]) & set(b["enums"])):
        gone = sorted(set(a["enums"][name]["values"]) - set(b["enums"][name]["values"]))
        if gone:
            removed_values.append({"enum": name, "values": gone})
    ta, tb = set(old.get("tweak_records", {})), set(new.get("tweak_records", {}))

    def cap(items):
        return items[:limit]

    out = {
        "old": {"version": (old.get("game_version") or {}).get("exe_file_version"), "patch": (old.get("game_version") or {}).get("patch")},
        "new": {"version": (new.get("game_version") or {}).get("exe_file_version"), "patch": (new.get("game_version") or {}).get("patch")},
        "summary": {"classes_removed": len(removed_classes), "classes_added": len(added_classes),
                    "members_removed": len(removed_members), "members_added": len(added_members),
                    "signatures_changed": len(changed), "classes_reparented": len(reparented),
                    "enums_removed": len(set(a["enums"]) - set(b["enums"])), "enum_values_removed": sum(len(e["values"]) for e in removed_values),
                    "globals_removed": len(set(a["globals"]) - set(b["globals"])),
                    "globals_added": len(set(b["globals"]) - set(a["globals"])),
                    "tweak_records_removed": len(ta - tb), "tweak_records_added": len(tb - ta)},
        "classes_removed": cap(removed_classes), "classes_added": cap(added_classes),
        "members_removed": cap(removed_members), "members_added": cap(added_members),
        "signatures_changed": cap(changed), "classes_reparented": cap(reparented),
        "enums_removed": cap(sorted(set(a["enums"]) - set(b["enums"]))), "enum_values_removed": cap(removed_values),
        "globals_removed": cap(sorted(set(a["globals"]) - set(b["globals"]))),
        "globals_added": cap(sorted(set(b["globals"]) - set(a["globals"]))),
        "tweak_records_removed": cap(sorted(ta - tb)), "tweak_records_added": cap(sorted(tb - ta)),
        "scope": "game API only (vanilla scripts + native RTTI) and vanilla TweakDB source; installed mods are ignored",
    }
    if old.get("schema") != new.get("schema"):
        out["note"] = (f"indexes have different schemas ({old.get('schema')} vs {new.get('schema')}); tweak record "
                       "counts may differ because of the parser, not the patch. Rebuild both for an exact record diff.")
    return out


def affected_hooks(d: dict, files: list[Path]) -> list[dict]:
    """Hooks in the given .reds files that point at something the patch removed."""
    gone_classes = set(d["classes_removed"])
    gone_members = {(m["class"], m["member"]) for m in d["members_removed"]}
    hits = []
    for f in files:
        lines = read_text(f).splitlines()
        for i, line in enumerate(lines):
            a = ANNOT.match(line.split("//", 1)[0])
            if not a or not a.group(2):
                continue
            cls = a.group(2)
            member = None
            for nxt in lines[i + 1:i + 8]:
                m = R_FUNC.match(nxt) or R_FIELD.match(nxt)
                if m:
                    member = m.group("name") if "name" in m.groupdict() else m.group(2)
                    break
            if cls in gone_classes:
                hits.append({"file": str(f), "line": i + 1, "hook": a.group(1), "class": cls, "why": "class removed"})
            elif member and (cls, member) in gone_members and a.group(1) in ("wrapMethod", "replaceMethod"):
                hits.append({"file": str(f), "line": i + 1, "hook": a.group(1), "class": cls, "member": member,
                             "why": "method removed"})
    return hits
