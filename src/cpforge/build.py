"""Build steps that turn source/ into game/: RED4ext plugins (CMake) and archives (WolvenKit CLI)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .game import find_tool
from .project import load_manifest
from .util import ForgeError, home_dir


def _run(cmd: list[str], cwd: Path, timeout: int) -> dict:
    t = time.time()
    env = dict(os.environ)
    # Let FetchContent's git write the SDK's long generated header paths on Windows.
    n = int(env.get("GIT_CONFIG_COUNT", "0") or 0)
    env.update({"GIT_CONFIG_COUNT": str(n + 1), f"GIT_CONFIG_KEY_{n}": "core.longpaths", f"GIT_CONFIG_VALUE_{n}": "true"})
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        return {"cmd": cmd, "exit_code": None, "timed_out": True, "seconds": round(time.time() - t, 1),
                "tail": "\n".join(out.strip().splitlines()[-25:]) + f"\n(stopped after {timeout} s)"}
    except OSError as e:
        raise ForgeError(f"cannot run {cmd[0]}: {e}", "check the tool path (cpforge doctor lists it)") from e
    out = (p.stdout or "") + (p.stderr or "")
    return {"cmd": cmd, "exit_code": p.returncode, "seconds": round(time.time() - t, 1),
            "tail": "\n".join(out.strip().splitlines()[-25:])}


def build_red4ext(root: Path, m: dict, config: str = "Release") -> dict:
    src = root / "source" / "red4ext"
    if not (src / "CMakeLists.txt").is_file():
        return {"skipped": "no source/red4ext/CMakeLists.txt"}
    cmake = find_tool("cmake")
    if not cmake:
        raise ForgeError("CMake not found", "install CMake and Visual Studio Build Tools (C++ workload)")
    bdir = src / "build"
    # The SDK has very long generated header paths; under a deep project folder
    # git's checkout silently skips files past MAX_PATH and the build fails with
    # C1083. Keep fetched dependencies in a short folder under the forge home.
    deps = home_dir() / "deps"
    deps.mkdir(parents=True, exist_ok=True)
    steps = [_run([cmake, "-S", str(src), "-B", str(bdir), "-A", "x64", f"-DFETCHCONTENT_BASE_DIR={deps}"], src, 900)]
    if steps[-1]["exit_code"] == 0:
        steps.append(_run([cmake, "--build", str(bdir), "--config", config], src, 1800))
    ok = all(s["exit_code"] == 0 for s in steps)
    result = {"ok": ok, "steps": steps}
    if ok:
        dlls = sorted(bdir.rglob(f"{config}/*.dll")) or sorted(bdir.rglob("*.dll"))
        dlls = [d for d in dlls if d.stem.lower() == m["id"].lower()] or dlls
        if not dlls:
            result.update(ok=False, error="build finished but no DLL was found")
        else:
            dest = root / "game" / "red4ext" / "plugins" / m["id"] / f"{m['id']}.dll"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dlls[0], dest)
            result["dll"] = str(dest)
    return result


def build_archive(root: Path, m: dict) -> dict:
    src = root / "source" / "archive"
    resources = [p for p in src.rglob("*") if p.is_file() and p.suffix.lower() not in (".md", ".txt")] if src.is_dir() else []
    if not resources:
        return {"skipped": "no source/archive/ resources yet"}
    wk = find_tool("wolvenkit")
    if not wk:
        return {"ok": False, "gap": "WolvenKit CLI not found (set WOLVENKIT_CLI to WolvenKit.CLI.exe); archive not packed"}
    with tempfile.TemporaryDirectory(prefix="cpforge-wk-") as td:
        step = _run([wk, "pack", str(src), "-o", td], root, 1800)
        packed = sorted(Path(td).glob("*.archive"))
        if step["exit_code"] != 0 or not packed:
            return {"ok": False, "steps": [step], "error": "WolvenKit pack produced no .archive"}
        dest = root / "game" / "archive" / "pc" / "mod" / f"{m['id']}.archive"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(packed[0], dest)
    return {"ok": True, "steps": [step], "archive": str(dest)}


def build(root: Path, config: str = "Release") -> dict:
    m = load_manifest(root)
    results = {"red4ext": build_red4ext(root, m, config), "archive": build_archive(root, m)}
    ok = all(r.get("ok", True) for r in results.values() if "skipped" not in r)
    return {"project": m["id"], "ok": ok, **results}
