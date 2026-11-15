"""Collect and triage the game's mod logs. Read-only."""
from __future__ import annotations

import glob
import os
import re
import time
from pathlib import Path

from .redscript import mod_of, parse_scc_output
from .util import KNOWLEDGE_DIR, load_json, read_text, rel

BAD = re.compile(r"\[(error|err|critical|fatal)\]|\berror\b|stack traceback|exception|failed", re.I)
WARN = re.compile(r"\[(warn|warning)\]", re.I)
NOISE = re.compile(r"0 errors|no errors|errors: 0|error_reporter|ErrorReporter", re.I)


def _newest(root: Path, pattern: str) -> Path | None:
    # glob.escape keeps '[' or '?' in the game path literal.
    hits = [Path(p) for p in glob.glob(os.path.join(glob.escape(str(root)), pattern))]
    hits = [h for h in hits if h.is_file()]
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None


def _signatures() -> list[dict]:
    try:
        return load_json(KNOWLEDGE_DIR / "errors.json")["signatures"]
    except (OSError, ValueError, KeyError):
        return []


def explain(text: str) -> list[dict]:
    out = []
    for s in _signatures():
        if re.search(s["pattern"], text, re.I):
            out.append({"id": s["id"], "meaning": s["meaning"], "fix": s["fix"], "tier": s["tier"]})
    return out


def _scan_generic(path: Path, root: Path, max_lines: int) -> dict:
    text = read_text(path)
    errors, warns, seen = [], [], set()
    for line in text.splitlines():
        s = line.strip()
        if not s or NOISE.search(s):
            continue
        key = re.sub(r"^\[[^\]]*\]\s*", "", s)[:200]
        if key in seen:
            continue
        if BAD.search(s):
            seen.add(key)
            errors.append(s[:400])
        elif WARN.search(s):
            seen.add(key)
            warns.append(s[:400])
    return {"file": rel(path, root), "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime)),
            "error_count": len(errors), "warning_count": len(warns), "errors": errors[:max_lines],
            "warnings": warns[: max(5, max_lines // 3)], "explain": explain("\n".join(errors[:200]))}


def collect(game_root: Path, max_lines: int = 25, mod: str | None = None) -> dict:
    report: dict = {"game": str(game_root), "sources": []}
    rs = game_root / "r6/logs/redscript_rCURRENT.log"
    if rs.is_file():
        text = read_text(rs)
        parsed = parse_scc_output(text, focus=mod)
        report["redscript"] = {
            "file": rel(rs, game_root),
            "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(rs.stat().st_mtime)),
            "compiled": parsed["complete"],
            "errors": [{k: d.get(k) for k in ("mod", "file", "line", "code", "message", "detail")} for d in parsed["errors"][:max_lines]],
            "warning_count": len(parsed["warnings"]),
            "warnings_by_mod": _by_mod(parsed["warnings"]),
            "explain": explain(text if parsed["errors"] else ""),
        }
    patterns = [
        "red4ext/logs/red4ext*.log", "red4ext/logs/game*.log",
        "red4ext/plugins/ArchiveXL/ArchiveXL*.log", "red4ext/plugins/TweakXL/TweakXL*.log",
        "red4ext/plugins/Codeware/Codeware*.log", "red4ext/logs/input_loader*.log", "red4ext/logs/mod_settings*.log",
        "bin/x64/plugins/cyber_engine_tweaks/cyber_engine_tweaks.log", "bin/x64/plugins/cyber_engine_tweaks/scripting.log",
    ]
    for pat in patterns:
        p = _newest(game_root, pat)
        if p:
            report["sources"].append(_scan_generic(p, game_root, max_lines))
    cet_mods = game_root / "bin/x64/plugins/cyber_engine_tweaks/mods"
    cet = []
    for p in sorted(cet_mods.glob("*/*.log")):
        if mod and mod.lower() not in str(p).lower():
            continue
        r = _scan_generic(p, game_root, max_lines)
        if r["error_count"]:
            cet.append(r)
    report["cet_mod_logs_with_errors"] = cet
    other = []
    newest: dict[str, Path] = {}  # plugin logs rotate per launch; only the latest run matters
    for p in (game_root / "red4ext/logs").glob("*.log"):
        key = re.sub(r"-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}$", "", p.stem.lower())
        if key not in newest or p.stat().st_mtime > newest[key].stat().st_mtime:
            newest[key] = p
    for key, p in sorted(newest.items()):
        if key.startswith(("red4ext", "game", "input_loader", "mod_settings")):
            continue
        r = _scan_generic(p, game_root, 5)
        if r["error_count"]:
            other.append({"file": r["file"], "error_count": r["error_count"], "first": r["errors"][:3]})
    report["plugin_logs_with_errors"] = other[-30:]
    report["crash_reports"] = crash_reports()
    if mod:
        report["filter"] = mod
        report["sources"] = [s for s in report["sources"] if any(mod.lower() in e.lower() for e in s["errors"])] or report["sources"]
    return report


def _by_mod(diags: list[dict]) -> dict:
    out: dict[str, int] = {}
    for d in diags:
        out[d.get("mod") or "?"] = out.get(d.get("mod") or "?", 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1])[:20])


def crash_reports(limit: int = 5) -> list[dict]:
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "REDEngine" / "ReporterQueue"
    if not base.is_dir():
        return []
    dirs = sorted((d for d in base.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime, reverse=True)
    out = []
    for d in dirs[:limit]:
        out.append({"folder": d.name, "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(d.stat().st_mtime)),
                    "files": sorted(f.name for f in d.iterdir())[:10]})
    return out
