"""Find mods that fight over the same thing: script hooks, archive resources, TweakDB records."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .archive import read_archive
from .tweakdb import parse_yaml
from .util import ForgeError, iter_files, rel, resource_hash


def script_conflicts(idx: dict) -> dict:
    by_target = defaultdict(list)
    for h in idx["api"]["hooks"]:
        if h["origin"].startswith("mod:"):
            by_target[(h["kind"], h["class"], h["member"])].append(h)
    replace, added, wraps = [], [], []
    for (kind, cls, member), hooks in by_target.items():
        mods = sorted({h["origin"][4:] for h in hooks})
        target = f"{cls}.{member}" if cls else member
        where = [f"{h['file']}:{h['line']}" for h in hooks]
        if kind in ("replaceMethod", "replaceGlobal") and len(mods) > 1:
            replace.append({"target": target, "kind": kind, "mods": mods, "where": where,
                            "meaning": "only one replacement survives; the others' changes are lost"})
        elif kind in ("addMethod", "addField") and len(mods) > 1:
            added.append({"target": target, "kind": kind, "mods": mods, "where": where,
                          "meaning": "the same member added twice: a compile error unless the mods guard it"})
        elif kind == "wrapMethod":
            wraps.append({"target": target, "count": len(hooks), "mods": mods})
    # A replace plus wraps on the same method: wraps still run, but order matters.
    replaced = {r["target"] for r in replace}
    for (kind, cls, member), hooks in by_target.items():
        if kind == "replaceMethod" and len({h["origin"] for h in hooks}) == 1:
            replaced.add(f"{cls}.{member}")
    wraps.sort(key=lambda w: -w["count"])
    return {"replace_conflicts": sorted(replace, key=lambda r: r["target"]),
            "duplicate_additions": sorted(added, key=lambda r: r["target"]),
            "most_wrapped": wraps[:25],
            "replaced_and_wrapped": sorted(w["target"] for w in wraps if w["target"] in replaced)[:50]}


def archive_files(game_root: Path) -> list[Path]:
    files = sorted((game_root / "archive/pc/mod").glob("*.archive"))
    files += sorted((game_root / "mods").glob("*/archives/*.archive"))
    return files


def archive_conflicts(game_root: Path, limit: int = 60) -> dict:
    owners = defaultdict(list)
    unreadable = []
    files = archive_files(game_root)
    names: dict[int, str] = {}
    for a in files:
        try:
            arc = read_archive(a)
        except ForgeError as e:
            unreadable.append({"archive": rel(a, game_root), "error": str(e)})
            continue
        for n in arc.names:
            names[resource_hash(n)] = n
        for h in arc.hashes:
            owners[h].append(a)
    pairs = defaultdict(list)
    for h, arcs in owners.items():
        if len(arcs) > 1:
            key = tuple(sorted(rel(x, game_root) for x in arcs))
            pairs[key].append(h)
    out = []
    for key, hashes in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
        out.append({"archives": list(key), "shared_resources": len(hashes),
                    "examples": [names.get(h, f"{h:016x}") for h in hashes[:5]]})
    return {"archives_scanned": len(files), "overlapping_sets": len(out), "overlaps": out[:limit],
            "unreadable": unreadable,
            "note": "Overlap means two archives ship the same resource path; which copy the game uses depends on load "
                    "order. Many overlaps are intended (patches, compatibility files). Names show only when an archive "
                    "embeds an uncompressed name list."}


def _is_tagged(v) -> bool:
    """An array operation: `!append x` on the value, or on every list item (`- !append x`)."""
    if isinstance(v, dict):
        return "$tag" in v
    return isinstance(v, list) and bool(v) and all(isinstance(i, dict) and "$tag" in i for i in v)


def _mod_name(relpath: str) -> str:
    parts = relpath.split("/")
    return parts[2] if len(parts) > 3 else parts[-1]


def tweak_conflicts(game_root: Path, limit: int = 100) -> dict:
    """Plain values set by several mods clash (one wins); array tags such as !append combine."""
    setters: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))  # record.field -> value repr -> mods
    touched: dict[str, set] = defaultdict(set)
    unreadable = []
    for f in iter_files(game_root / "r6/tweaks", (".yaml", ".yml")):
        r = rel(f, game_root)
        mod = _mod_name(r)
        try:
            doc = parse_yaml(f) or {}
        except Exception as e:  # third-party file; report and move on
            unreadable.append({"file": r, "error": str(e)[:160]})
            continue
        if not isinstance(doc, dict):
            continue
        for key, value in doc.items():
            key = str(key)
            if isinstance(value, dict) and "$tag" not in value:
                touched[key].add(mod)
                for field, v in value.items():
                    if str(field).startswith("$") or _is_tagged(v):
                        continue
                    setters[f"{key}.{field}"][repr(v)].add(mod)
            else:
                touched[key.rsplit(".", 1)[0]].add(mod)
                if not _is_tagged(value):
                    setters[key][repr(value)].add(mod)
    clashes = []
    for target, values in setters.items():
        mods = set().union(*values.values())
        if len(values) > 1 and len(mods) > 1:
            clashes.append({"field": target, "mods": sorted(mods), "different_values": len(values)})
    clashes.sort(key=lambda c: (-len(c["mods"]), c["field"]))
    shared = sum(1 for mods in touched.values() if len(mods) > 1)
    return {"value_clashes": len(clashes), "clashes": clashes[:limit], "records_touched_by_several_mods": shared,
            "unreadable": unreadable[:20],
            "note": "A clash is the same field set to different plain values by different mods: one wins by load order. "
                    "Records only extended with array tags (!append...) by several mods are normal and not listed."}
