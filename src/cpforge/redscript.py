"""redscript: offline compile with the game's scc.exe, and static hook checks against the index."""
from __future__ import annotations

import difflib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import index as idxmod
from .util import ForgeError, iter_files, read_text

ERR_HEAD = re.compile(r"^\[(ERROR|WARN)[^\]]*\]\s*(.*)$")
AT = re.compile(r"At (.+?):(\d+):(\d+):")


def parse_scc_output(text: str, focus: str | None = None) -> dict:
    """Group scc / redscript log lines into diagnostics. Each starts at an [ERROR or [WARN line."""
    diags: list[dict] = []
    cur = None
    for line in text.splitlines():
        m = ERR_HEAD.match(line)
        if m:
            cur = {"level": m.group(1).lower(), "message": m.group(2).strip(), "detail": []}
            at = AT.search(m.group(2))
            if at:
                cur.update(file=at.group(1), line=int(at.group(2)), col=int(at.group(3)))
            diags.append(cur)
        elif line.startswith("[INFO") or line.startswith("[DEBUG"):
            cur = None
        elif cur is not None and line.strip() and len(cur["detail"]) < 8:
            cur["detail"].append(line.rstrip())
    for d in diags:
        code =re.search(r"\b([A-Z][A-Z_]{3,})\b", " ".join([d["message"]] + d["detail"]))
        d["code"] = code.group(1) if code else None
        d["mod"] = mod_of(d.get("file", ""))
    if focus:
        mine = [d for d in diags if focus.lower() in (d.get("file", "") + " ".join(d["detail"])).lower()]
    else:
        mine = diags
    return {
        "errors": [d for d in mine if d["level"] == "error"],
        "warnings": [d for d in mine if d["level"] == "warn"],
        "other_errors": len([d for d in diags if d["level"] == "error"]) - len([d for d in mine if d["level"] == "error"]),
        "complete": "Compilation complete" in text or "Output successfully saved" in text,
    }


def mod_of(path: str) -> str | None:
    p = path.replace("\\", "/")
    for marker in ("/r6/scripts/", "/scripts/", "/red4ext/plugins/"):
        if marker in p:
            rest = p.split(marker, 1)[1]
            return rest.split("/", 1)[0] if "/" in rest else rest
    return None


def scc_path(game_root: Path) -> Path:
    p = game_root / "engine/tools/scc.exe"
    if not p.is_file():
        raise ForgeError("redscript compiler not found (engine/tools/scc.exe)", "install redscript into the game")
    return p


def compile_scripts(game_root: Path, script_dirs: list[Path], mod_name: str, deps: list[str] | str = "auto",
                    timeout: int = 180, keep: Path | None = None) -> dict:
    """Compile the given script folders with selected dependencies in a scratch copy.

    The live r6/cache is never written: scc gets <tmp>/scripts and <tmp>/cache.
    """
    if os.name != "nt":
        raise ForgeError("scc.exe compile needs Windows", "run this on the machine with the game installed")
    scc = scc_path(game_root)
    base = game_root / "r6/cache/final.redscripts"
    if not base.is_file():
        raise ForgeError("r6/cache/final.redscripts missing", "verify the game files in your launcher")
    work = Path(keep) if keep else Path(tempfile.mkdtemp(prefix="cpforge-scc-"))
    try:
        scripts = work / "scripts"
        if scripts.exists():
            shutil.rmtree(scripts)
        scripts.mkdir(parents=True)
        (work / "cache").mkdir(exist_ok=True)
        if not (work / "cache/final.redscripts").is_file():
            shutil.copy2(base, work / "cache/final.redscripts")
        installed = game_root / "r6/scripts"
        if deps == "all":
            dep_names = [p.name for p in installed.iterdir()] if installed.is_dir() else []
        elif deps in ("auto", "none", None):
            dep_names = []
        else:
            dep_names = list(deps)
        missing = []
        for name in dep_names:
            if name.lower() == mod_name.lower() or name.startswith("__"):
                continue
            src = installed / name
            if src.is_dir():
                shutil.copytree(src, scripts / name, ignore=shutil.ignore_patterns("__folder_managed_by_vortex"))
            elif src.is_file() and src.suffix == ".reds":
                shutil.copy2(src, scripts / name)
            else:
                missing.append(name)
        dest = scripts / mod_name
        dest.mkdir(parents=True, exist_ok=True)
        for d in script_dirs:
            for f in iter_files(d, (".reds",)):
                target = dest / f.relative_to(d)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
        # Plugins ship their own .reds (Codeware, Mod Settings, ...): hand them to scc as extra paths.
        paths = []
        if deps != "none":
            for plugin in sorted((game_root / "red4ext/plugins").glob("*/")):
                if any(plugin.rglob("*.reds")):
                    paths.append(str(plugin))
        (work / "paths.txt").write_text("\n".join(paths) + ("\n" if paths else ""), encoding="utf-8")
        out = work / "final.redscripts.modded"
        if out.exists():
            out.unlink()
        cmd = [str(scc), "-compile", str(scripts), "-compilePathsFile", str(work / "paths.txt"),
               "-outputCacheFile", str(out)]
        try:
            proc = subprocess.run(cmd, cwd=str(scc.parent), capture_output=True, text=True, timeout=timeout,
                                  errors="replace")
            text = (proc.stdout or "") + (proc.stderr or "")
            code = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired as e:
            text = (e.stdout or "") if isinstance(e.stdout, str) else ""
            code = None
            timed_out = True
            subprocess.run(["taskkill", "/F", "/IM", "scc.exe"], capture_output=True)
        result = parse_scc_output(text, focus=mod_name)
        # Point diagnostics at the project's own files, not the scratch copy.
        prefix = str(dest).lower().replace("/", "\\")
        for d in result["errors"] + result["warnings"]:
            f = d.get("file", "")
            if f.lower().replace("/", "\\").startswith(prefix):
                tail = f[len(prefix):].lstrip("\\/")
                for sd in script_dirs:
                    cand = sd / tail
                    if cand.is_file():
                        d["file"] = str(cand)
                        break
            d["message"] = d["message"].replace(str(work), "<scratch>")
        summary = [d for d in result["errors"] if "compilation has failed" in d["message"].lower()]
        if summary and len(summary) < len(result["errors"]):
            result["errors"] = [d for d in result["errors"] if d not in summary]
        result.update({"exit_code": code, "timed_out": timed_out, "dependencies": dep_names, "missing_dependencies": missing,
                       "plugin_script_paths": len(paths), "output_written": out.is_file(),
                       "scratch": str(work) if keep else None})
        if timed_out or (code not in (0, None) and not result["errors"]):
            tail = "\n".join(text.splitlines()[-15:])
            result["log_tail"] = tail
            if "stack overflow" in text.lower() or code == 3221225725:
                result["hint"] = ("scc overflowed its stack: compile with fewer dependencies (--deps), and avoid huge "
                                  "array literals or very long string '+' chains")
        result["ok"] = (not timed_out) and not result["errors"] and result["complete"]
        return result
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)


HOOK = re.compile(r"^\s*@(wrapMethod|replaceMethod|addMethod|addField|replaceGlobal)\s*\(\s*(\w*)\s*\)")
MEMBER = re.compile(r"^\s*(?:(?:public|private|protected|final|static|native|cb|const|persistent|exec|quest)\s+)*(func|let)\s+(\w+)")


def static_check(files: list[Path], idx: dict | None, installed_version_hint: str | None = None) -> list[dict]:
    """Check hook targets exist in the installed game, and flag syntax older compilers reject."""
    findings = []
    classes = idx["api"]["classes"] if idx else {}
    for f in files:
        lines = read_text(f).splitlines()
        for i, line in enumerate(lines):
            if re.search(r"\bcontinue\s*;", line.split("//", 1)[0]):
                findings.append({"level": "warning", "file": str(f), "line": i + 1, "code": "RS-CONTINUE",
                                 "message": "'continue' needs redscript 1.0+; 0.5.x compilers reject it (UNRESOLVED_REF)"})
            m = HOOK.match(line)
            if not m or not idx:
                continue
            kind, cls = m.group(1), m.group(2)
            member = None
            for j in range(i + 1, min(i + 8, len(lines))):
                nxt = lines[j].strip()
                mm = MEMBER.match(lines[j])
                if mm:
                    member = mm.group(2)
                    break
                if nxt and not nxt.startswith(("@", "//")):
                    break
            if kind == "replaceGlobal":
                continue
            if cls not in classes:
                close = difflib.get_close_matches(cls, list(classes), n=3)
                findings.append({"level": "error", "file": str(f), "line": i + 1, "code": "RS-NO-CLASS",
                                 "message": f"@{kind}({cls}): no class '{cls}' in the installed game or mods",
                                 "suggest": close})
                continue
            if kind in ("wrapMethod", "replaceMethod") and member:
                hit = idxmod.find_member(idx, cls, member)
                if not hit:
                    names = [fn["name"] for c in idxmod.class_chain(idx, cls) for fn in classes[c]["funcs"]]
                    findings.append({"level": "error", "file": str(f), "line": i + 1, "code": "RS-NO-METHOD",
                                     "message": f"@{kind}({cls}) {member}: no such method on {cls} or its parents",
                                     "suggest": difflib.get_close_matches(member, names, n=3)})
                elif hit.get("owner") != cls and hit.get("origin") != "native":
                    findings.append({"level": "warning", "file": str(f), "line": i + 1, "code": "RS-INHERITED",
                                     "message": f"{member} is declared on {hit['owner']}, not {cls}; wrap it there unless {cls} overrides it"})
            if kind in ("addMethod", "addField") and member:
                if idxmod.find_member(idx, cls, member) and not idxmod.find_member(idx, cls, member).get("origin", "").startswith("mod:"):
                    findings.append({"level": "error", "file": str(f), "line": i + 1, "code": "RS-ADD-EXISTS",
                                     "message": f"@{kind}({cls}) {member}: the game already has this member"})
    return findings
