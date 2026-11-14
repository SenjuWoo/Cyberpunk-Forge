"""Deterministic release ZIPs from a project's game/ folder, and checks on any mod ZIP."""
from __future__ import annotations

import fnmatch
import hashlib
import io
import re
import time
import zipfile
from pathlib import Path, PurePosixPath

from . import __version__
from .project import load_manifest
from .util import ForgeError, iter_files, save_json, sha256_file

FIXED_TIME = (1980, 1, 1, 0, 0, 0)
ALLOWED_ROOTS = ("r6/scripts/", "r6/tweaks/", "r6/input/", "r6/audioware/", "archive/pc/mod/",
                 "bin/x64/plugins/cyber_engine_tweaks/mods/", "red4ext/plugins/", "mods/", "engine/config/")
DEV_EXCLUDE = (".git/*", "*/.git/*", "*__pycache__*", "*.pyc", "*.bak", "*.tmp", "*.orig", "*.log", "*.vortex_backup",
               "*.DS_Store", "*Thumbs.db", "*desktop.ini", "*__folder_managed_by_vortex", "*.blend1", "*.cpforge*")
DEV_FILES = ("STATE.md", "PLAN.md", "DECISIONS.md", "VALIDATION.md", "WORKSPACE_OWNERSHIP.md", "AGENTS.md", "CLAUDE.md",
             "cpforge.json", "CURRENT.txt")
SECRET_PATTERNS = [
    ("openrouter-key", re.compile(r"sk-or-v1-[A-Fa-f0-9]{32,}")),
    ("openai-style-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}")),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}")),
    ("aws-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]
TEXT_EXT = {".reds", ".lua", ".yaml", ".yml", ".xl", ".xml", ".json", ".md", ".txt", ".tweak", ".csv", ".ini", ".toml",
            ".cfg", ".script"}


def _excluded(relpath: str, extra: list[str]) -> bool:
    return any(fnmatch.fnmatch(relpath, pat) for pat in (*DEV_EXCLUDE, *extra))


def scan_secrets(name: str, data: bytes) -> list[dict]:
    if PurePosixPath(name).suffix.lower() not in TEXT_EXT or len(data) > 4 << 20:
        return []
    text = data.decode("utf-8", "replace")
    found = []
    for label, rx in SECRET_PATTERNS:
        for m in rx.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            found.append({"file": name, "line": line, "kind": label, "match": m.group(0)[:6] + "..."})
    return found


def build(root: Path, out: Path | None = None) -> dict:
    m = load_manifest(root)
    game = root / "game"
    if not game.is_dir():
        raise ForgeError("project has no game/ folder", "put runtime files under game/<game-relative path>")
    extra = m.get("package", {}).get("exclude", [])
    files = []
    for f in iter_files(game):
        relp = f.relative_to(game).as_posix()
        if not _excluded(relp, extra) and PurePosixPath(relp).name not in DEV_FILES:
            files.append((relp, f))
    if not files:
        raise ForgeError("game/ has no files to package")
    dist = out or (root / "dist")
    dist.mkdir(parents=True, exist_ok=True)
    zpath = dist / f"{m['id']}-{m['version']}.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for relp, f in sorted(files, key=lambda x: x[0].lower()):
            info = zipfile.ZipInfo(relp, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 0
            z.writestr(info, f.read_bytes())
    zpath.write_bytes(buf.getvalue())
    digest = sha256_file(zpath)
    (dist / (zpath.name + ".sha256")).write_text(f"{digest}  {zpath.name}\n", encoding="utf-8")
    receipt = {"tool": f"cpforge {__version__}", "project": m["id"], "version": m["version"],
               "built": time.strftime("%Y-%m-%dT%H:%M:%S"), "zip": zpath.name, "sha256": digest,
               "inputs": [{"path": r, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()} for r, f in sorted(files)],
               "not_covered": ["runtime load in game", "gameplay"]}
    save_json(dist / f"{m['id']}-{m['version']}.receipt.json", receipt)
    result = {"zip": str(zpath), "sha256": digest, "files": len(files)}
    result["validation"] = validate(zpath)
    return result


def validate(zpath: Path) -> dict:
    findings = []

    def add(level, code, msg, **kw):
        findings.append(dict(level=level, code=code, message=msg, **kw))

    try:
        z = zipfile.ZipFile(zpath)
    except (OSError, zipfile.BadZipFile) as e:
        raise ForgeError(f"not a readable zip: {zpath} ({e})") from e
    with z:
        names = z.namelist()
        lower_seen: dict[str, str] = {}
        cet_dirs, plugin_dirs, archives, xls = set(), set(), set(), set()
        times = set()
        for info in z.infolist():
            n = info.filename
            times.add(info.date_time)
            # zipfile turns "\\" into "/" on Windows when reading; the raw name is orig_filename.
            if "\\" in info.orig_filename:
                add("error", "PKG-BACKSLASH", "path uses backslashes; mod managers expect '/'", file=n)
            if n.startswith("/") or re.match(r"^[A-Za-z]:", n) or ".." in PurePosixPath(n).parts:
                add("error", "PKG-UNSAFE-PATH", "absolute or parent path", file=n)
            low = n.lower()
            if low in lower_seen and lower_seen[low] != n:
                add("error", "PKG-CASE-DUP", f"same path twice with different case: {lower_seen[low]}", file=n)
            lower_seen[low] = n
            if n.endswith("/"):
                continue
            norm = n.replace("\\", "/")
            if not norm.startswith(ALLOWED_ROOTS):
                add("warning", "PKG-ROOT", "file outside the usual game folders (check the install root)", file=n)
            base = PurePosixPath(norm).name
            if base in DEV_FILES or _excluded(norm, []):
                add("error", "PKG-DEV-FILE", "development or tool file in a release package", file=n)
            if base.lower().startswith("changelog"):
                add("warning", "PKG-CHANGELOG", "changelog inside the package; Nexus has its own changelog tab", file=n)
            if info.file_size == 0:
                add("warning", "PKG-EMPTY", "zero-byte file", file=n)
            if norm.startswith("bin/x64/plugins/cyber_engine_tweaks/mods/"):
                parts = norm.split("/")
                if len(parts) > 6:
                    cet_dirs.add(parts[5])
            if norm.startswith("red4ext/plugins/") and norm.count("/") >= 3:
                plugin_dirs.add(norm.split("/")[2])
            if norm.startswith("r6/scripts/") and not norm.endswith((".reds", ".md", ".txt", ".json")):
                add("warning", "PKG-SCRIPTS-EXT", "non-.reds file under r6/scripts", file=n)
            if norm.startswith("r6/scripts/") and norm.count("/") == 2:
                add("warning", "PKG-LOOSE-REDS", "script directly in r6/scripts; use r6/scripts/<ModName>/", file=n)
            if norm.endswith(".archive"):
                archives.add(norm)
            if norm.endswith(".archive.xl"):
                xls.add(norm)
            for s in scan_secrets(norm, z.read(info)):
                add("error", "PKG-SECRET", f"looks like a {s['kind']} ({s['match']}); never ship credentials",
                    file=s["file"], line=s["line"])
        for d in sorted(cet_dirs):
            if f"bin/x64/plugins/cyber_engine_tweaks/mods/{d}/init.lua" not in names:
                add("error", "PKG-CET-INIT", f"CET mod folder '{d}' has no init.lua")
        for d in sorted(plugin_dirs):
            if not any(n.startswith(f"red4ext/plugins/{d}/") and n.lower().endswith(".dll") for n in names):
                add("warning", "PKG-PLUGIN-DLL", f"red4ext/plugins/{d} ships no .dll (fine only if it is script-only)")
        for x in sorted(xls):
            if x[: -len(".xl")] not in archives:
                add("warning", "PKG-XL-ORPHAN", "ArchiveXL file without a matching .archive in this package", file=x)
    errors = [f for f in findings if f["level"] == "error"]
    return {"zip": str(zpath), "files": len([n for n in names if not n.endswith("/")]), "ok": not errors,
            "deterministic_timestamps": len(times) <= 1, "errors": errors,
            "warnings": [f for f in findings if f["level"] == "warning"]}
