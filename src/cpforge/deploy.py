"""Explicit install of a project into a game folder for testing, with a receipt and a way back.

deploy copies game/ into the game root, records every file and its hash, and
backs up anything it would overwrite. undeploy removes only files whose hash
still matches what deploy wrote, then restores the backups. Neither runs
unless asked; neither touches mod-manager staging.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from .package import DEV_FILES, _excluded
from .project import load_manifest
from .util import ForgeError, iter_files, load_json, save_json, sha256_file

RECEIPT = ".cpforge/deploy-receipt.json"


def deploy(root: Path, game_root: Path, dry_run: bool = False, force: bool = False) -> dict:
    m = load_manifest(root)
    src = root / "game"
    if not src.is_dir():
        raise ForgeError("project has no game/ folder")
    receipt_path = root / RECEIPT
    previous = load_json(receipt_path) if receipt_path.is_file() else None
    if previous and Path(previous["game"]).resolve() != game_root.resolve():
        raise ForgeError("this project is deployed to another game folder", "run cpforge undeploy first")
    owned = {f["path"]: f for f in (previous or {}).get("files", [])}
    plan, blocked = [], []
    for f in iter_files(src):
        relp = f.relative_to(src).as_posix()
        if _excluded(relp, []) or Path(relp).name in DEV_FILES:
            continue
        dest = game_root / relp
        if dest.exists() and relp not in owned and not force:
            blocked.append(relp)
        plan.append((relp, f, dest))
    vortex = (game_root / "vortex.deployment.json").is_file()
    result = {"project": m["id"], "game": str(game_root), "files": len(plan), "dry_run": dry_run,
              "vortex_managed_game": vortex}
    if vortex:
        result["note"] = ("Vortex manages this game folder: it will report these files as external changes. "
                          "Undeploy before the next Vortex deployment, or package the mod and install it through Vortex.")
    if blocked:
        result["blocked"] = blocked[:50]
        result["error"] = "files already exist that this project did not deploy; pass --force to back them up and overwrite"
        if not dry_run:
            raise ForgeError(result["error"], "inspect the listed files, then rerun with --force if overwriting is intended")
    if dry_run:
        result["would_write"] = [p for p, _, _ in plan][:200]
        return result
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_root = root / ".cpforge" / "backup" / stamp
    files = []
    for relp, f, dest in plan:
        backup = owned.get(relp, {}).get("backup")
        if dest.exists() and relp not in owned:
            b = backup_root / relp
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, b)
            backup = str(b)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        files.append({"path": relp, "sha256": sha256_file(dest), "backup": backup})
    # Files deployed last time but gone from the project now are removed too.
    current = {p for p, _, _ in plan}
    stale = [p for p in owned if p not in current]
    removed = _remove(game_root, [owned[p] for p in stale])
    save_json(receipt_path, {"project": m["id"], "version": m["version"], "game": str(game_root),
                             "deployed": time.strftime("%Y-%m-%dT%H:%M:%S"), "files": files})
    result.update({"written": len(files), "backed_up": len([f for f in files if f["backup"]]),
                   "stale_removed": removed, "receipt": str(receipt_path),
                   "next": "start the game; then cpforge logs --mod " + m["id"]})
    return result


def _remove(game_root: Path, entries: list[dict]) -> dict:
    removed, kept, restored = [], [], []
    for e in entries:
        dest = game_root / e["path"]
        if dest.is_file():
            if sha256_file(dest) != e["sha256"]:
                kept.append(e["path"])
                continue
            dest.unlink()
            removed.append(e["path"])
        if e.get("backup") and Path(e["backup"]).is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(e["backup"], dest)
            restored.append(e["path"])
        parent = dest.parent
        while parent != game_root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    return {"removed": len(removed), "restored": restored, "kept_changed": kept}


def undeploy(root: Path, dry_run: bool = False) -> dict:
    receipt_path = root / RECEIPT
    if not receipt_path.is_file():
        raise ForgeError("nothing deployed from this project (no receipt)")
    r = load_json(receipt_path)
    game_root = Path(r["game"])
    if dry_run:
        return {"would_remove": [f["path"] for f in r["files"]], "game": str(game_root)}
    out = _remove(game_root, r["files"])
    receipt_path.unlink()
    out.update({"game": str(game_root), "project": r["project"]})
    if out["kept_changed"]:
        out["note"] = "files changed after deploy were left in place"
    return out
