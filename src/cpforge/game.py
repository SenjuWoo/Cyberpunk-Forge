"""Find the installed game and read what is installed. Read-only."""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
from pathlib import Path

from .util import KNOWLEDGE_DIR, ForgeError, file_version, load_json

EXE = Path("bin/x64/Cyberpunk2077.exe")
STEAM_APP = "Cyberpunk 2077"
GOG_ID = "1423049311"


def is_game_root(path: Path) -> bool:
    return (path / EXE).is_file()


def _steam_libraries() -> list[Path]:
    roots: list[Path] = []
    steam = None
    if os.name == "nt":
        try:
            import winreg

            for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        for name in ("SteamPath", "InstallPath"):
                            try:
                                steam = Path(winreg.QueryValueEx(k, name)[0])
                                break
                            except OSError:
                                continue
                except OSError:
                    continue
                if steam:
                    break
        except ImportError:
            pass
    else:
        for cand in (Path.home() / ".steam/steam", Path.home() / ".local/share/Steam"):
            if cand.is_dir():
                steam = cand
                break
    if steam:
        roots.append(steam)
        vdf = steam / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            text = vdf.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'"path"\s+"([^"]+)"', text):
                roots.append(Path(m.group(1).replace("\\\\", "\\")))
    return roots


def _gog_paths() -> list[Path]:
    out: list[Path] = []
    if os.name != "nt":
        return out
    try:
        import winreg

        for key in (rf"SOFTWARE\WOW6432Node\GOG.com\Games\{GOG_ID}", rf"SOFTWARE\GOG.com\Games\{GOG_ID}"):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
                    out.append(Path(winreg.QueryValueEx(k, "path")[0]))
            except OSError:
                continue
    except ImportError:
        pass
    return out


def _epic_paths() -> list[Path]:
    out: list[Path] = []
    base = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Epic/EpicGamesLauncher/Data/Manifests"
    for item in glob.glob(str(base / "*.item")):
        try:
            data = json.loads(Path(item).read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if "cyberpunk" in str(data.get("DisplayName", "")).lower() and data.get("InstallLocation"):
            out.append(Path(data["InstallLocation"]))
    return out


def candidates() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for env in ("CP2077_ROOT", "CYBERPUNK2077_ROOT"):
        if os.environ.get(env):
            out.append((f"env:{env}", Path(os.environ[env])))
    for lib in _steam_libraries():
        out.append(("steam", lib / "steamapps" / "common" / STEAM_APP))
    for p in _gog_paths():
        out.append(("gog", p))
    for p in _epic_paths():
        out.append(("epic", p))
    return out


def find_game(explicit: str | None = None) -> tuple[Path | None, str, list[str]]:
    """Return (root, how it was found, places checked)."""
    checked: list[str] = []
    if explicit:
        p = Path(explicit)
        if is_game_root(p):
            return p, "argument", [str(p)]
        raise ForgeError(f"not a Cyberpunk 2077 folder (no {EXE.as_posix()}): {p}",
                         "pass the folder that contains bin/x64/Cyberpunk2077.exe")
    seen = set()
    for how, p in candidates():
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        checked.append(str(p))
        if is_game_root(p):
            return p, how, checked
    return None, "", checked


def require_game(explicit: str | None) -> Path:
    root, _, checked = find_game(explicit)
    if root is None:
        raise ForgeError("Cyberpunk 2077 install not found",
                         "pass --game <folder> or set CP2077_ROOT; checked: " + ("; ".join(checked) or "nothing"))
    return root


def game_version(root: Path) -> dict:
    facts = load_json(KNOWLEDGE_DIR / "facts.json")["facts"]
    fv = file_version(root / EXE)
    patch = facts["game.versions"]["value"].get(fv or "", None)
    return {
        "exe_file_version": fv,
        "patch": patch,
        "phantom_liberty": (root / "archive/pc/ep1").is_dir(),
        "note": None if patch else ("version not readable on this OS" if fv is None
                                    else "file version not in the forge's table; update knowledge/facts.json"),
    }


def frameworks(root: Path) -> list[dict]:
    reg = load_json(KNOWLEDGE_DIR / "frameworks.json")
    out = []
    for fw in reg["frameworks"]:
        present = all((root / m).exists() for m in fw["markers"])
        ver = None
        if present and fw.get("version_from"):
            ver = file_version(root / fw["version_from"])
        out.append({"id": fw["id"], "name": fw["name"], "installed": present, "version": ver,
                    "role": fw["role"], "repo": fw.get("repo"), "nexus": fw.get("nexus")})
    return out


def framework_map(root: Path) -> dict[str, dict]:
    return {f["id"]: f for f in frameworks(root)}


def find_tool(tool_id: str) -> str | None:
    reg = load_json(KNOWLEDGE_DIR / "frameworks.json")
    for t in reg["tools"]:
        if t["id"] != tool_id:
            continue
        if t.get("env") and os.environ.get(t["env"]):
            p = os.environ[t["env"]]
            return p if Path(p).exists() or shutil.which(p) else None
        for name in t["names"]:
            hit = shutil.which(name)
            if hit:
                return hit
    return None


def tools() -> list[dict]:
    reg = load_json(KNOWLEDGE_DIR / "frameworks.json")
    return [{"id": t["id"], "name": t["name"], "path": find_tool(t["id"]), "role": t["role"]} for t in reg["tools"]]


def _count(path: Path, pattern: str) -> int:
    return len(glob.glob(str(path / pattern))) if path.is_dir() else 0


def inventory(root: Path) -> dict:
    cet = root / "bin/x64/plugins/cyber_engine_tweaks/mods"
    redmod = []
    mods_json = root / "r6/cache/modded/mods.json"
    if mods_json.is_file():
        try:
            for m in load_json(mods_json).get("mods", []):
                redmod.append({"folder": m.get("folder"), "enabled": m.get("enabled"), "deployed": m.get("deployed"),
                               "version": m.get("deployedVersion")})
        except (OSError, ValueError):
            pass
    return {
        "game": str(root),
        "vortex_managed": (root / "vortex.deployment.json").is_file() or (root / "r6/scripts/__folder_managed_by_vortex").exists(),
        "surfaces": {
            "redscript_mods": _count(root / "r6/scripts", "*/"),
            "redscript_loose_files": _count(root / "r6/scripts", "*.reds"),
            "tweak_mods": _count(root / "r6/tweaks", "*"),
            "archives": _count(root / "archive/pc/mod", "*.archive"),
            "archive_xl": _count(root / "archive/pc/mod", "*.xl"),
            "cet_mods": _count(cet, "*/"),
            "red4ext_plugins": _count(root / "red4ext/plugins", "*/"),
            "input_xml": _count(root / "r6/input", "*.xml"),
            "audioware_mods": _count(root / "r6/audioware", "*/"),
            "redmod_mods": _count(root / "mods", "*/"),
        },
        "redmod_deployed": redmod,
        "redmod_sources": {
            "scripts": (root / "tools/redmod/scripts").is_dir(),
            "tweaks": (root / "tools/redmod/tweaks").is_dir(),
            "metadata": (root / "tools/redmod/metadata.json").is_file(),
        },
    }
