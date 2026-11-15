"""Explicit install of a project into a game folder for testing, with a receipt and a way back.

deploy copies game/ into the game root, records every file and its hash, and
backs up anything it would overwrite. undeploy removes only files whose hash
still matches what deploy wrote, then restores the backups. Neither runs
unless asked; neither touches mod-manager staging.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from .package import DEV_FILES, _excluded
from .project import load_manifest
from .util import ForgeError, iter_files, load_json, save_json, sha256_file

RECEIPT = ".cpforge/deploy-receipt.json"


def _put(src: Path, dest: Path) -> None:
    """Copy src to dest by writing a sibling file and renaming it over dest.

    Mod managers deploy by hard link, so a game file and its staging copy can be
    one file. Opening dest for writing would change the staging copy too; a
    rename only replaces the name the game folder has for it.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".cpforge-tmp")
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


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
    plan, blocked, changed = [], [], []
    for f in iter_files(src):
        relp = f.relative_to(src).as_posix()
        if _excluded(relp, []) or Path(relp).name in DEV_FILES:
            continue
        dest = game_root / relp
        if dest.exists() and relp not in owned:
            blocked.append(relp)
        elif dest.is_file() and relp in owned:
            # Deployed before: if it no longer holds what was written, it was edited in the game folder.
            now = sha256_file(dest)
            if now != owned[relp]["sha256"] and now != sha256_file(f):
                changed.append(relp)
        plan.append((relp, f, dest))
    vortex = (game_root / "vortex.deployment.json").is_file()
    result = {"project": m["id"], "game": str(game_root), "files": len(plan), "dry_run": dry_run,
              "vortex_managed_game": vortex}
    if vortex:
        result["note"] = ("Vortex manages this game folder: it will report these files as external changes. "
                          "Undeploy before the next Vortex deployment, or package the mod and install it through Vortex.")
    if blocked:
        result["blocked"] = blocked[:50]
    if changed:
        result["changed_since_deploy"] = changed[:50]
    if (blocked or changed) and not force:
        parts = []
        if blocked:
            parts.append("files already exist that this project did not deploy")
        if changed:
            parts.append("files deployed earlier were edited in the game folder")
        result["error"] = "; ".join(parts) + "; pass --force to back them up and overwrite"
        if not dry_run:
            raise ForgeError(result["error"] + " (" + ", ".join((blocked + changed)[:8]) + ")",
                             "inspect the listed files (cpforge deploy --dry-run), then rerun with --force if "
                             "overwriting is intended")
    if dry_run:
        result["would_write"] = [p for p, _, _ in plan][:200]
        return result
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_root = root / ".cpforge" / "backup" / stamp
    files, changed_copies = [], []
    at = None
    try:
        for relp, f, dest in plan:
            at = relp
            backup = owned.get(relp, {}).get("backup")
            if dest.exists() and relp not in owned:
                b = backup_root / relp
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, b)
                backup = str(b)
            elif relp in changed:
                # The receipt keeps the pre-deploy original as `backup`; the edited copy is saved beside it.
                b = backup_root / "edited-after-deploy" / relp
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, b)
                changed_copies.append(str(b))
            _put(f, dest)
            files.append({"path": relp, "sha256": sha256_file(dest), "backup": backup})
    except OSError as e:
        # Record what is in the game folder now, so undeploy can take it back out.
        done = {f["path"] for f in files}
        save_json(receipt_path, {"project": m["id"], "version": m["version"], "game": str(game_root),
                                 "deployed": time.strftime("%Y-%m-%dT%H:%M:%S"), "incomplete": True,
                                 "files": files + [e2 for p, e2 in owned.items() if p not in done]})
        raise ForgeError(f"deploy stopped at {at}: {e}",
                         f"{len(files)} file(s) were written and are in the receipt; close the game if it holds the "
                         "file, then rerun cpforge deploy, or take them back out with cpforge undeploy") from e
    # Files deployed last time but gone from the project now are removed too.
    current = {p for p, _, _ in plan}
    stale = [p for p in owned if p not in current]
    removed = _remove(game_root, [owned[p] for p in stale])
    save_json(receipt_path, {"project": m["id"], "version": m["version"], "game": str(game_root),
                             "deployed": time.strftime("%Y-%m-%dT%H:%M:%S"), "files": files})
    result.update({"written": len(files), "backed_up": len([f for f in files if f["backup"]]),
                   "stale_removed": removed, "receipt": str(receipt_path),
                   "next": "start the game; then cpforge logs --mod " + m["id"]})
    if changed_copies:
        result["changed_backed_up"] = changed_copies
    return result


def _remove(game_root: Path, entries: list[dict]) -> dict:
    removed, kept, restored, left = [], [], [], []
    for e in entries:
        dest = game_root / e["path"]
        if dest.is_file():
            if sha256_file(dest) != e["sha256"]:
                kept.append(e["path"])
                if e.get("backup") and Path(e["backup"]).is_file():
                    left.append({"path": e["path"], "backup": e["backup"]})
                continue
            dest.unlink()
            removed.append(e["path"])
        if e.get("backup") and Path(e["backup"]).is_file():
            _put(Path(e["backup"]), dest)
            restored.append(e["path"])
        parent = dest.parent
        while parent != game_root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    out = {"removed": len(removed), "restored": restored, "kept_changed": kept}
    if left:
        out["backups_not_restored"] = left
    return out


def undeploy(root: Path, dry_run: bool = False) -> dict:
    receipt_path = root / RECEIPT
    if not receipt_path.is_file():
        raise ForgeError("nothing deployed from this project (no receipt)")
    r = load_json(receipt_path)
    game_root = Path(r["game"])
    if dry_run:
        return {"would_remove": [f["path"] for f in r["files"]], "game": str(game_root)}
    if not game_root.is_dir():
        raise ForgeError(f"the game folder this project was deployed to is not reachable: {game_root}",
                         "reconnect the drive or restore the folder, then run cpforge undeploy again; the receipt is kept")
    out = _remove(game_root, r["files"])
    receipt_path.unlink()
    out.update({"game": str(game_root), "project": r["project"]})
    if out["kept_changed"]:
        out["note"] = ("files changed after deploy were left in place; any original they replaced is listed in "
                       "backups_not_restored")
    return out
