"""cpforge command line. Every command prints JSON; exit 0 = ok, 1 = findings, 2 = named failure, 3 = bug."""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from . import __version__
from .util import ForgeError, emit, home_dir, resource_hash, tweakdb_id


def _game(args):
    from .game import require_game
    return require_game(getattr(args, "game", None))


def _project(args):
    from .project import find_project
    return find_project(getattr(args, "project", None))


def cmd_doctor(args):
    from .doctor import run
    return run(args.game, args.require_game)


def cmd_capabilities(args):
    p = parser()
    cmds = []
    for action in p._subparsers._group_actions:  # generated from the parser, never a hand-kept list
        for name, sub in action.choices.items():
            opts = []
            for a in sub._actions:
                if a.dest in ("help",):
                    continue
                opts.append({"name": a.option_strings[0] if a.option_strings else a.dest,
                             "required": bool(a.required) or not a.option_strings, "help": a.help or ""})
            cmds.append({"command": name, "help": sub.description or "", "args": opts})
    return {"forge": "Cyberpunk Forge", "version": __version__, "commands": cmds,
            "global": ["--game <folder>"], "exit_codes": {"0": "ok", "1": "findings", "2": "named failure", "3": "bug"}}, 0


def cmd_plan(args):
    from .knowledge import plan
    return plan(" ".join(args.request)), 0


def cmd_knowledge(args):
    from .knowledge import doc, docs
    if args.name:
        return {"name": args.name, "text": doc(args.name)}, 0
    return {"docs": docs(), "hint": "cpforge knowledge <name>"}, 0


def cmd_facts(args):
    from .knowledge import facts
    return {"facts": facts(args.key)}, 0


def cmd_game(args):
    from .game import frameworks, game_version, inventory
    root = _game(args)
    return {"version": game_version(root), "frameworks": frameworks(root), "inventory": inventory(root)}, 0


def cmd_index(args):
    from .index import build
    root = _game(args)
    idx = build(root, include_mods=not args.vanilla_only)
    return {"built": idx["built"], "counts": idx["counts"], "seconds": idx["seconds"],
            "game_version": idx["game_version"], "stored_in": str(home_dir() / "index")}, 0


def cmd_api(args):
    from . import index as I
    if args.action == "versions":
        return {"stored": I.stored_versions(), "stored_in": str(home_dir() / "index")}, 0
    if args.action == "diff":
        if len(args.query) != 2:
            raise ForgeError("api diff needs two versions", "cpforge api diff <old> <new>  (see cpforge api versions)")
        d = I.diff(I.load_version(args.query[0]), I.load_version(args.query[1]), args.limit)
        if args.project or (Path.cwd() / "cpforge.json").is_file():
            from .util import iter_files
            root = _project(args)
            d["project_hooks_affected"] = I.affected_hooks(d, list(iter_files(root / "game", (".reds",))))
        return d, (1 if d.get("project_hooks_affected") else 0)
    if not args.query:
        raise ForgeError(f"api {args.action} needs a name or text", f"cpforge api {args.action} <query>")
    args.query = " ".join(args.query)
    idx = I.load(_game(args))
    if args.action == "class":
        classes = idx["api"]["classes"]
        name = args.query
        if name not in classes:
            return {"error": f"no class {name}", "close": [r["name"] for r in I.search(idx, name, "class", 8)]}, 1
        c = classes[name]
        hooks = [h for h in idx["api"]["hooks"] if h["class"] == name]
        members = c["funcs"] if args.members == "funcs" else c["fields"] if args.members == "fields" else c["funcs"] + c["fields"]
        if args.filter:
            members = [x for x in members if args.filter.lower() in x["name"].lower()]
        return {"class": name, "kind": c["kind"], "chain": I.class_chain(idx, name), "origin": c["origin"],
                "where": f"{c['file']}:{c['line']}" if c["file"] else c["origin"],
                "members": members[: args.limit], "member_count": len(c["funcs"]) + len(c["fields"]),
                "mod_hooks": [{k: h[k] for k in ("kind", "member", "origin")} for h in hooks][:40]}, 0
    if args.action == "enum":
        e = idx["api"]["enums"].get(args.query)
        return ({"enum": args.query, **e}, 0) if e else ({"error": f"no enum {args.query}"}, 1)
    return {"query": args.query, "results": I.search(idx, args.query, args.kind, args.limit)}, 0


def cmd_tweak(args):
    from . import index as I
    from .tweakdb import TweakDB
    args.query = " ".join(args.query)
    root = _game(args)
    tdb = TweakDB(root)
    idx = I.load(root, required=False)
    if args.action == "show":
        name = args.query
        out = {"record": name, "exists_in_tweakdb": tdb.exists(name), "tweakdb_id": f"{tweakdb_id(name):#012x}"}
        key = tdb.type_key(name)
        if key is not None and idx:
            out["type"] = idx["record_types"].get(str(key), f"unknown type key {key:#x}")
        src = idx["tweak_records"].get(name) if idx else None
        if src:
            out["source"] = src
            lines = (root / src["file"]).read_text(encoding="utf-8", errors="replace").splitlines()
            start = src["line"] - 1
            block, depth = [], 0
            for ln in lines[start:start + 400]:
                block.append(ln)
                depth += ln.count("{") - ln.count("}")
                if depth <= 0 and "}" in ln:
                    break
            out["definition"] = "\n".join(block)
        from .tweakdb import installed_yaml_records
        mods = installed_yaml_records(root).get(name)
        if mods:
            out["changed_by_installed_tweaks"] = mods
        return out, (0 if out["exists_in_tweakdb"] or src or mods else 1)
    if args.action == "exists":
        names = [n.strip() for n in args.query.split(",") if n.strip()]
        in_bin = {n: tdb.exists(n) for n in names}
        # Some vanilla records exist only in the .tweak sources (Vehicle.vehicle_list on 2.5).
        in_src = {n: bool(idx and n in idx["tweak_records"]) for n in names}
        res = {n: in_bin[n] or in_src[n] for n in names}
        where = {n: ("tweakdb.bin" if in_bin[n] else "vanilla .tweak source" if in_src[n] else None) for n in names}
        return {"exists": res, "found_in": where, "sources": tdb.sources + (["index of tools/redmod/tweaks"] if idx else [])}, \
            (0 if all(res.values()) else 1)
    words = args.query.lower().split()
    names = tdb.names() or (list(idx["tweak_records"]) if idx else [])
    hits = [n for n in names if all(w in n.lower() for w in words)]
    hits.sort(key=lambda n: (len(n), n))
    return {"query": args.query, "count": len(hits), "results": hits[: args.limit],
            "name_source": tdb.sources or (["index of tools/redmod/tweaks"] if idx else [])}, 0


def cmd_res(args):
    from . import resource as R
    results = []
    game_map = None
    if args.action != "roundtrip" and not args.no_game:
        from .game import find_game
        try:
            game_map = R.game_hashes(find_game(args.game)[0])
        except ForgeError:
            game_map = None  # reported per file as references.unresolved = null
    trees: dict[str, dict] = {}
    for f in args.files:
        p = Path(f)
        if args.action == "roundtrip":
            results.append(R.roundtrip(p))
            continue
        root = Path(args.root) if args.root else R.project_root_of(p)
        names = trees.setdefault(str(root), R.tree_hashes(root)) if root else {}
        try:
            doc = R.load(p)
        except ForgeError as e:
            results.append({"file": str(p), "ok": False, "errors": [{"code": "RES-READ", "message": str(e)}],
                            "warnings": [], "fix": e.fix})
            continue
        ref_findings, ref_summary = R.reference_check(doc, names, game_map)
        R.name_hashes(doc, names)
        r = R.check(doc)
        r["warnings"] += [{k: v for k, v in x.items() if k != "level"} for x in ref_findings]
        r["references"] = ref_summary
        r["file"] = str(p)
        if args.action == "check":
            r.pop("summary", None)
        results.append(r)
    ok = all(r.get("ok") for r in results)
    return ({"results": results} if len(results) > 1 else results[0]), (0 if ok else 1)


def cmd_hash(args):
    out = []
    for v in args.values:
        if args.tweakdb:
            out.append({"name": v, "tweakdb_id": f"{tweakdb_id(v):#012x}"})
        else:
            out.append({"path": v, "fnv1a64": f"{resource_hash(v):016x}", "decimal": resource_hash(v)})
    return {"hashes": out}, 0


def cmd_archive(args):
    from .archive import find_resource, read_archive
    if args.action == "info":
        arc = read_archive(Path(args.target))
        out = arc.summary()
        if args.names:
            out["names"] = arc.names[: args.limit]
        return out, 0
    root = _game(args)
    from .conflicts import archive_files
    files = archive_files(root)
    if args.vanilla:
        files += sorted((root / "archive/pc/content").glob("*.archive")) + sorted((root / "archive/pc/ep1").glob("*.archive"))
    hits = find_resource(args.target, files)
    return {"resource": args.target, "fnv1a64": f"{resource_hash(args.target):016x}", "archives": hits,
            "searched": len(files)}, (0 if hits else 1)


def cmd_conflicts(args):
    from . import conflicts as C
    from . import index as I
    root = _game(args)
    what = args.what
    out = {}
    if what in ("all", "scripts"):
        out["scripts"] = C.script_conflicts(I.load(root))
    if what in ("all", "archives"):
        out["archives"] = C.archive_conflicts(root, args.limit)
    if what in ("all", "tweaks"):
        out["tweaks"] = C.tweak_conflicts(root, args.limit)
    if what in ("all", "scripts"):
        out["note"] = "script hooks come from the index; rerun cpforge index after installing or removing mods"
    return out, 0


def cmd_logs(args):
    from .logs import collect
    return collect(_game(args), args.lines, args.mod), 0


def cmd_new(args):
    from .project import new_project
    out = Path(args.out) if args.out else Path.cwd() / args.name.replace(" ", "")
    return new_project(args.name, args.kind or ["redscript"], out, args.author or "", args.description or "", args.force), 0


def cmd_templates(args):
    from .project import templates
    return {"templates": [{"kind": k, "title": v.get("title"), "requires": [r["id"] for r in v.get("requires", [])],
                           "notes": v.get("notes", "")} for k, v in templates().items()]}, 0


def cmd_check(args):
    from .check import check_project
    res = check_project(_project(args), args.game, args.compile)
    return res, (0 if res["ok"] else 1)


def cmd_compile(args):
    from .project import load_manifest
    from .redscript import compile_scripts
    root = _project(args)
    m = load_manifest(root)
    game = _game(args)
    dirs = [p for p in (root / "game/r6/scripts").glob("*") if p.is_dir()] or [root / "game/r6/scripts"]
    deps = args.deps.split(",") if args.deps not in ("auto", "all", "none") else args.deps
    if deps == "auto":
        deps = m.get("script_dependencies") or []
    res = compile_scripts(game, dirs, m["id"], deps, args.timeout, Path(args.keep) if args.keep else None)
    return res, (0 if res["ok"] else 1)


def cmd_build(args):
    from .build import build
    res = build(_project(args), args.config)
    return res, (0 if res["ok"] else 1)


def cmd_package(args):
    from .package import build
    res = build(_project(args), Path(args.out) if args.out else None)
    return res, (0 if res["validation"]["ok"] else 1)


def cmd_validate(args):
    from .package import validate
    res = validate(Path(args.zip))
    return res, (0 if res["ok"] else 1)


def cmd_deploy(args):
    from .deploy import deploy
    return deploy(_project(args), _game(args), args.dry_run, args.force), 0


def cmd_undeploy(args):
    from .deploy import undeploy
    return undeploy(_project(args), args.dry_run), 0


def cmd_bump(args):
    from .project import bump
    return bump(_project(args), args.part), 0


def cmd_nexus(args):
    from .nexus import kit
    return kit(_project(args)), 0


def cmd_explain(args):
    from .logs import explain
    hits = explain(" ".join(args.text))
    return {"matches": hits, "hint": None if hits else "no known signature; cpforge logs shows the surrounding lines"}, 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cpforge", description="Cyberpunk Forge: make, check and ship Cyberpunk 2077 mods.")
    p.add_argument("--version", action="version", version=f"cpforge {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, desc):
        sp = sub.add_parser(name, description=desc, help=desc)
        sp.add_argument("--game", help="game folder (default: auto-detect, or CP2077_ROOT)")
        sp.set_defaults(fn=fn)
        return sp

    s = add("doctor", cmd_doctor, "health: CLI, forge payload, game, frameworks, index, tools")
    s.add_argument("--require-game", action="store_true", help="fail when the game is not found")
    add("capabilities", cmd_capabilities, "list commands and arguments (generated from the parser)")
    s = add("plan", cmd_plan, "route a request: which surface, templates, docs, steps, what to avoid")
    s.add_argument("request", nargs="+", help="what you want to make or fix, in words")
    s = add("knowledge", cmd_knowledge, "list knowledge docs or print one")
    s.add_argument("name", nargs="?", help="doc name, e.g. redscript")
    s = add("facts", cmd_facts, "versioned facts with provenance (formats, versions, layouts)")
    s.add_argument("key", nargs="?", help="substring of a fact key, e.g. archive")
    add("game", cmd_game, "installed game version, frameworks and mod inventory")
    s = add("index", cmd_index, "build the local API and TweakDB index from the installed game")
    s.add_argument("--vanilla-only", action="store_true", help="skip installed mods' .reds")
    s = add("api", cmd_api, "look up classes, functions, fields and enums from the installed game")
    s.add_argument("action", choices=["search", "class", "enum", "versions", "diff"],
                   help="search <text> | class <Name> | enum <Name> | versions | diff <old> <new>")
    s.add_argument("query", nargs="*", help="text, exact name, or two versions for diff (exe version or patch, e.g. 2.31 2.5)")
    s.add_argument("--project", help="diff: also list this project's hooks that hit removed API")
    s.add_argument("--kind", default="any", choices=["any", "class", "func", "field", "enum"], help="search filter")
    s.add_argument("--members", default="all", choices=["all", "funcs", "fields"], help="class members to list")
    s.add_argument("--filter", help="only members whose name contains this")
    s.add_argument("--limit", type=int, default=60, help="max results")
    s = add("tweak", cmd_tweak, "TweakDB records: search names, show vanilla source, check existence")
    s.add_argument("action", choices=["search", "show", "exists"], help="search <words> | show <Record> | exists <A,B>")
    s.add_argument("query", nargs="+", help="words, a record name, or comma-separated names")
    s.add_argument("--limit", type=int, default=60, help="max results")
    s = add("res", cmd_res, "game resources via WolvenKit JSON: check, inspect (.mesh/.app/.ent), byte round trip")
    s.add_argument("action", choices=["check", "inspect", "roundtrip"],
                   help="check: structural rules | inspect: rules + summary (components, lights, slots) | roundtrip")
    s.add_argument("files", nargs="+", help="CR2W resource files or their WolvenKit .json")
    s.add_argument("--root", help="archive source root for resolving references (default: the <project>/source/archive the file is in)")
    s.add_argument("--no-game", action="store_true", help="skip looking references up in the game's archives")
    s = add("hash", cmd_hash, "FNV-1a 64 resource-path hash, or TweakDBID with --tweakdb")
    s.add_argument("values", nargs="+", help="paths or record names")
    s.add_argument("--tweakdb", action="store_true", help="hash as TweakDB record names")
    s = add("archive", cmd_archive, "read an .archive index, or find which archives contain a resource path")
    s.add_argument("action", choices=["info", "find"], help="info <file.archive> | find <resource path>")
    s.add_argument("target", help="archive file or resource path")
    s.add_argument("--names", action="store_true", help="info: print embedded names when present")
    s.add_argument("--vanilla", action="store_true", help="find: include the game's own archives")
    s.add_argument("--limit", type=int, default=200, help="max names")
    s = add("conflicts", cmd_conflicts, "mods fighting over script hooks, archive resources, TweakDB records")
    s.add_argument("--what", default="all", choices=["all", "scripts", "archives", "tweaks"], help="which kind")
    s.add_argument("--limit", type=int, default=60, help="max entries per list")
    s = add("logs", cmd_logs, "collect and triage redscript, RED4ext, CET, ArchiveXL, TweakXL, Codeware logs and crash reports")
    s.add_argument("--mod", help="only lines mentioning this mod")
    s.add_argument("--lines", type=int, default=25, help="max lines per source")
    s = add("explain", cmd_explain, "match an error message against the known-error registry")
    s.add_argument("text", nargs="+", help="error text")
    add("templates", cmd_templates, "list project templates")
    s = add("new", cmd_new, "create a mod project from one or more templates")
    s.add_argument("name", help="mod name")
    s.add_argument("--kind", action="append", help="template kind (repeatable): see cpforge templates")
    s.add_argument("--out", help="project folder (default: ./<Name>)")
    s.add_argument("--author", help="author name for the manifest")
    s.add_argument("--description", help="one-line description")
    s.add_argument("--force", action="store_true", help="add to a non-empty folder")
    for name, fn, desc in (("check", cmd_check, "validate a project against the installed game"),
                           ("compile", cmd_compile, "compile the project's redscript with the game's scc.exe (scratch copy)"),
                           ("build", cmd_build, "build source/: RED4ext plugin (CMake), archive (WolvenKit CLI)"),
                           ("package", cmd_package, "deterministic release zip from game/, with validation and receipt"),
                           ("deploy", cmd_deploy, "copy game/ into the game folder for testing (receipt + backups)"),
                           ("undeploy", cmd_undeploy, "remove what deploy wrote and restore backups"),
                           ("bump", cmd_bump, "bump the version everywhere and keep the last good zip"),
                           ("nexus", cmd_nexus, "write a Nexus page kit (BBCode, changelog, file description)")):
        s = add(name, fn, desc)
        s.add_argument("--project", help="project folder (default: current folder or a parent with cpforge.json)")
        if name == "check":
            s.add_argument("--compile", action="store_true", help="also compile redscript with scc.exe")
        if name == "compile":
            s.add_argument("--deps", default="auto", help="auto (manifest script_dependencies) | none | all | A,B")
            s.add_argument("--timeout", type=int, default=180, help="seconds before scc is stopped")
            s.add_argument("--keep", help="keep the scratch compile folder here")
        if name == "build":
            s.add_argument("--config", default="Release", choices=["Release", "Debug", "RelWithDebInfo"], help="CMake config")
        if name == "package":
            s.add_argument("--out", help="output folder (default: <project>/dist)")
        if name in ("deploy", "undeploy"):
            s.add_argument("--dry-run", action="store_true", help="show what would change")
        if name == "deploy":
            s.add_argument("--force", action="store_true", help="back up and overwrite files this project did not deploy")
        if name == "bump":
            s.add_argument("part", help="major | minor | patch | X.Y.Z")
    s = add("validate", cmd_validate, "check any mod zip: layout, dev files, secrets, CET init.lua, case clashes")
    s.add_argument("zip", help="zip file")
    return p


def _log(argv, code, seconds):
    try:
        d = home_dir() / "logs"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "cpforge.log", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "argv": argv, "exit": code, "s": seconds}) + "\n")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    args = parser().parse_args(argv)
    t = time.time()
    try:
        result, code = args.fn(args)
        emit(result)
    except ForgeError as e:
        emit({"error": str(e), "fix": e.fix})
        code = e.code
    except KeyboardInterrupt:
        code = 130
    except Exception as e:  # report bugs as JSON too, with the trace for the issue tracker
        emit({"error": f"internal error: {e}", "trace": traceback.format_exc().splitlines()[-6:],
              "fix": "report this with the command you ran"})
        code = 3
    _log(argv, code, round(time.time() - t, 2))
    return code
