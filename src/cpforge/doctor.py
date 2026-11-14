"""Health check. CLI health, forge payload, game discovery and toolchain are separate sections."""
from __future__ import annotations

import json
import os
import platform
import sys

from . import __version__
from . import index as idxmod
from .game import find_game, frameworks, game_version, inventory, tools
from .project import templates
from .util import KNOWLEDGE_DIR, TEMPLATES_DIR, ForgeError, home_dir

REQUIRED_KNOWLEDGE = ("facts.json", "frameworks.json", "routes.json", "errors.json")
CORE = ("redscript", "red4ext", "cet", "archivexl", "tweakxl", "codeware")


def run(game_arg: str | None = None, require_game: bool = False) -> tuple[dict, int]:
    report: dict = {"forge": {"version": __version__, "python": platform.python_version(), "platform": sys.platform,
                              "home": str(home_dir())}}
    problems = []
    # 1. CLI / toolchain
    py_ok = sys.version_info >= (3, 10)
    try:
        import yaml  # noqa: F401
        yaml_ok = True
    except ImportError:
        yaml_ok = False
    report["cli"] = {"status": "ok" if py_ok and yaml_ok else "fail", "python_3_10_plus": py_ok, "pyyaml": yaml_ok}
    if not py_ok:
        problems.append({"section": "cli", "problem": "Python 3.10+ required", "fix": "install Python 3.10 or newer"})
    if not yaml_ok:
        problems.append({"section": "cli", "problem": "PyYAML missing", "fix": "pip install pyyaml (or run Install.ps1)"})
    # 2. payload
    payload_bad = []
    for name in REQUIRED_KNOWLEDGE:
        p = KNOWLEDGE_DIR / name
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            payload_bad.append(f"{name}: {e}")
    tpls = templates() if TEMPLATES_DIR.is_dir() else {}
    if not tpls:
        payload_bad.append("templates/ missing or empty")
    report["payload"] = {"status": "ok" if not payload_bad else "fail", "templates": sorted(tpls),
                         "knowledge_docs": len(list(KNOWLEDGE_DIR.glob("*.md"))), "problems": payload_bad}
    if payload_bad:
        problems.append({"section": "payload", "problem": "; ".join(payload_bad), "fix": "reinstall or git checkout the forge"})
    # 3. game
    try:
        root, how, checked = find_game(game_arg)
    except ForgeError as e:
        root, how, checked = None, "", [str(e)]
    if root is None:
        report["game"] = {"status": "missing", "checked": checked,
                          "fix": "pass --game <folder with bin/x64/Cyberpunk2077.exe> or set CP2077_ROOT"}
        if require_game:
            problems.append({"section": "game", "problem": "game not found", "fix": report["game"]["fix"]})
    else:
        fws = frameworks(root)
        missing_core = [f["id"] for f in fws if f["id"] in CORE and not f["installed"]]
        idx = idxmod.load(root, required=False)
        report["game"] = {"status": "ok" if not missing_core else "warn", "root": str(root), "found_by": how,
                          "version": game_version(root), "frameworks": fws, "missing_core": missing_core,
                          "index": ({"built": idx["built"], "counts": idx["counts"]} if idx
                                    else {"built": None, "fix": "cpforge index"}),
                          "inventory": inventory(root)}
    # 4. tools (optional; a missing one only limits what can be checked)
    report["tools"] = tools()
    report["tools_note"] = "optional: WolvenKit CLI packs archives, luajit/luac checks Lua syntax, CMake builds RED4ext plugins"
    if os.name != "nt":
        report["tools_note"] += "; redscript compile and file versions need Windows"
    report["problems"] = problems
    report["ok"] = not problems
    return report, (0 if not problems else 1)
