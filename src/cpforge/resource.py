"""Game resources as WolvenKit JSON: byte round trip, structural checks, and a readable summary.

The rules here come from vanilla 2.5 vehicle files (every one passes) and from
mistakes that made `WolvenKit.CLI convert deserialize` fail or produced files
that load wrong. WolvenKit does the binary work; this module reads its JSON.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from .archive import read_archive
from .game import find_tool
from .util import ForgeError, resource_hash

RESOURCE_EXTS = (".ent", ".app", ".mesh", ".mi", ".mt", ".remt", ".xbm", ".mlsetup", ".mlmask", ".mltemplate",
                 ".inkatlas", ".inkwidget", ".json", ".csv", ".anims", ".rig", ".phys", ".animgraph", ".effect",
                 ".workspot", ".morphtarget", ".physicalscene", ".cfoliage", ".streamingsector", ".wem", ".bk2",
                 ".gradient", ".curveset", ".env", ".fx", ".particle", ".ies", ".scene", ".questphase", ".journal")


def wolvenkit() -> str:
    wk = find_tool("wolvenkit")
    if not wk:
        raise ForgeError("WolvenKit CLI not found", "set WOLVENKIT_CLI to WolvenKit.CLI.exe or put it on PATH (cpforge doctor)")
    return wk


def _wk(args: list[str], timeout: int = 600) -> dict:
    cmd = [wolvenkit(), *args, "-v", "Minimal"]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)
    out = (p.stdout or "") + (p.stderr or "")
    # WolvenKit can exit non-zero after a partial success (import with no mesh buffers), and zero after a
    # logged failure: read the log lines, not only the exit code.
    bad = [ln.strip() for ln in out.splitlines() if any(w in ln for w in ("Error", "Exception", "Failed", "could not"))]
    return {"exit_code": p.returncode, "errors": bad[:20], "log_tail": out.splitlines()[-12:]}


def serialize(path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    res = _wk(["convert", "serialize", str(path), "-o", str(out_dir)])
    out = out_dir / (path.name + ".json")
    if not out.is_file():
        raise ForgeError(f"WolvenKit could not serialize {path.name}: " + " | ".join(res["errors"] or res["log_tail"][-3:]),
                         "is it a CR2W resource (not raw/exported)?")
    return out


def deserialize(json_path: Path, out_dir: Path) -> tuple[Path | None, dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    res = _wk(["convert", "deserialize", str(json_path), "-o", str(out_dir)])
    name = json_path.name[: -len(".json")] if json_path.name.endswith(".json") else json_path.stem
    out = out_dir / name
    return (out if out.is_file() else None), res


def is_cr2w(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(4) == b"CR2W"


def load(path: Path) -> dict:
    """WolvenKit JSON for a .json file or any CR2W resource (serialized through WolvenKit)."""
    path = Path(path)
    if not path.is_file():
        raise ForgeError(f"no such file: {path}")
    if not is_cr2w(path):
        # Game .json resources (localization) are CR2W too; only text JSON is read directly.
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ForgeError(f"{path.name} is neither CR2W nor WolvenKit JSON ({e.__class__.__name__})") from e
    with tempfile.TemporaryDirectory(prefix="cpforge-res-") as td:
        return json.loads(serialize(path, Path(td)).read_text(encoding="utf-8-sig"))


def roundtrip(path: Path) -> dict:
    """CR2W -> JSON -> CR2W must give the same bytes; for a .json, JSON -> CR2W -> JSON must keep the data."""
    path = Path(path)
    with tempfile.TemporaryDirectory(prefix="cpforge-rt-") as td:
        t = Path(td)
        if not is_cr2w(path):
            built, res = deserialize(path, t / "bin")
            if not built:
                return {"file": str(path), "ok": False, "stage": "deserialize", "errors": res["errors"] or res["log_tail"]}
            back = json.loads(serialize(built, t / "json").read_text(encoding="utf-8-sig"))
            orig = json.loads(path.read_text(encoding="utf-8-sig"))
            same = _strip_header(orig) == _strip_header(back)
            return {"file": str(path), "ok": same, "direction": "json -> cr2w -> json",
                    "first_difference": None if same else _first_diff(_strip_header(orig), _strip_header(back))}
        js = serialize(path, t / "json")
        built, res = deserialize(js, t / "bin")
        if not built:
            return {"file": str(path), "ok": False, "stage": "deserialize", "errors": res["errors"] or res["log_tail"]}
        a, b = path.read_bytes(), built.read_bytes()
        diff = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
        if diff is None and len(a) != len(b):
            diff = min(len(a), len(b))
        return {"file": str(path), "ok": diff is None, "direction": "cr2w -> json -> cr2w", "size": len(a),
                "rebuilt_size": len(b), "first_differing_byte": diff}


def _strip_header(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "Header"}


def _first_diff(a, b, path: str = "") -> str | None:
    if type(a) is not type(b):
        return path or "/"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}/{k}"
            d = _first_diff(a[k], b[k], f"{path}/{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path} (length {len(a)} vs {len(b)})"
        for i, (x, y) in enumerate(zip(a, b)):
            d = _first_diff(x, y, f"{path}/{i}")
            if d:
                return d
        return None
    return None if a == b else (path or "/")


# --- generic JSON rules --------------------------------------------------------

def _walk(o, fn, path=""):
    fn(o, path)
    if isinstance(o, dict):
        for k, v in o.items():
            _walk(v, fn, f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk(v, fn, f"{path}/{i}")


def handle_index(doc: dict) -> dict[str, dict]:
    """HandleId -> Data over the whole document (WolvenKit numbers handles document-wide)."""
    out: dict[str, dict] = {}

    def fn(o, _):
        if isinstance(o, dict) and "HandleId" in o and "Data" in o:
            out.setdefault(str(o["HandleId"]), o["Data"])
    _walk(doc, fn)
    return out


def resolve(node, index: dict[str, dict]):
    if isinstance(node, dict):
        if "HandleRefId" in node:
            return index.get(str(node["HandleRefId"]))
        if "HandleId" in node and "Data" in node:
            return node["Data"]
    return node


def cname(v) -> str | None:
    if isinstance(v, dict):
        return v.get("$value")
    return v


def generic_checks(doc: dict) -> list[dict]:
    ids: Counter = Counter()
    refs: list[tuple[str, str]] = []
    paths_bad: list[str] = []

    def fn(o, path):
        if not isinstance(o, dict):
            return
        if "HandleId" in o:
            ids[str(o["HandleId"])] += 1
        if "HandleRefId" in o:
            refs.append((str(o["HandleRefId"]), path))
        if o.get("$type") == "ResourcePath" and o.get("$storage") == "uint64" and not isinstance(o.get("$value"), str):
            paths_bad.append(path)
    _walk(doc, fn)
    out = []
    dups = sorted((h for h, n in ids.items() if n > 1), key=lambda x: int(x) if x.isdigit() else 0)
    if dups:
        out.append({"level": "error", "code": "RES-HANDLE-DUP",
                    "message": f"{len(dups)} HandleId value(s) used more than once ({', '.join(dups[:8])}); handle ids are "
                               "document-wide, re-id copied handles or deserialize fails ('could not be converted to RedFileDto')"})
    dangling = sorted({r for r, _ in refs if r not in ids})
    if dangling:
        out.append({"level": "error", "code": "RES-HANDLE-DANGLING",
                    "message": f"HandleRefId points at missing HandleId(s): {', '.join(dangling[:8])}",
                    "where": [p for r, p in refs if r in dangling][:5]})
    if paths_bad:
        out.append({"level": "error", "code": "RES-PATH-UINT64",
                    "message": "a uint64-stored ResourcePath must hold a string ('0' when empty), not a number",
                    "where": paths_bad[:5]})
    buffers = []

    def fb(o, path):
        if isinstance(o, dict) and "BufferId" in o and isinstance(o.get("Data"), dict) and "Chunks" in o["Data"]:
            buffers.append(str(o["BufferId"]))
    _walk(doc, fb)
    bdup = sorted({b for b in buffers if buffers.count(b) > 1})
    if bdup:
        out.append({"level": "error", "code": "RES-BUFFER-DUP",
                    "message": f"compiledData BufferId repeated ({', '.join(bdup[:8])}); vanilla numbers them 0..n per file"})
    return out


# --- per type --------------------------------------------------------------------

def _chunks(compiled) -> list[dict]:
    data = (compiled or {}).get("Data") if isinstance(compiled, dict) else None
    return (data or {}).get("Chunks") or []


def _component(c: dict, index: dict) -> dict:
    out = {"type": c.get("$type"), "name": cname(c.get("name"))}
    mesh = c.get("mesh")
    if isinstance(mesh, dict) and mesh.get("DepotPath"):
        out["mesh"] = cname(mesh["DepotPath"])
        out["mesh_appearance"] = cname(c.get("meshAppearance"))
    pt = resolve(c.get("parentTransform"), index) if c.get("parentTransform") else None
    if isinstance(pt, dict):
        bind, slot = cname(pt.get("bindName")), cname(pt.get("slotName"))
        out["bound_to"] = bind + (f"/{slot}" if slot and slot != "None" else "") if bind else None
    if c.get("$type") == "vehicleLightComponent":
        out["light_type"] = c.get("lightType")
        out["material_zone"] = c.get("materialZone")
    return out


def _cruid_check(owner: str, compiled) -> list[dict]:
    """CruidDict maps every chunk index to that chunk's component id ('0' for the .ent's entity object)."""
    chunks = _chunks(compiled)
    cruid = ((compiled or {}).get("Data") or {}).get("CruidDict") if isinstance(compiled, dict) else None
    if not chunks or cruid is None:
        return []
    if len(cruid) != len(chunks):
        return [{"level": "error", "code": "RES-CRUID",
                 "message": f"{owner}: CruidDict has {len(cruid)} entries for {len(chunks)} chunks"}]
    wrong = [k for k, v in cruid.items() if not str(k).isdigit() or int(k) >= len(chunks)
             or str(chunks[int(k)].get("id", "0")) != str(v)]
    if wrong:
        return [{"level": "error", "code": "RES-CRUID",
                 "message": f"{owner}: CruidDict entries do not match the chunks' component ids (chunk {', '.join(wrong[:6])})"}]
    return []


def mesh_check(rc: dict) -> tuple[list[dict], dict]:
    out = []
    blob = (rc.get("renderResourceBlob") or {}).get("Data") or {}
    chunks = (blob.get("header") or {}).get("renderChunkInfos")
    entries = rc.get("materialEntries") or []
    names = [cname(e.get("name")) for e in entries]
    local = [e for e in entries if e.get("isLocalInstance")]
    external = [e for e in entries if not e.get("isLocalInstance")]
    n_local = len((rc.get("localMaterialBuffer") or {}).get("materials") or []) + len(rc.get("preloadLocalMaterialInstances") or [])
    n_ext = len(rc.get("externalMaterials") or []) + len(rc.get("preloadExternalMaterials") or [])
    if len(local) != n_local:
        out.append({"level": "error", "code": "RES-MESH-LOCAL-COUNT",
                    "message": f"{len(local)} local material entries but {n_local} local material instances "
                               "(localMaterialBuffer.materials + preloadLocalMaterialInstances)"})
    for kind, group, n in (("local", local, n_local), ("external", external, n_ext)):
        idx = [e.get("index") for e in group]
        if any(i is None or i < 0 or i >= max(n, 0) for i in idx) and n:
            out.append({"level": "error", "code": "RES-MESH-ENTRY-INDEX", "message": f"a {kind} material entry index is outside 0..{n - 1}"})
        if len(set(idx)) != len(idx):
            out.append({"level": "error", "code": "RES-MESH-ENTRY-INDEX", "message": f"two {kind} material entries share an index"})
    dupn = sorted({n for n in names if names.count(n) > 1})
    if dupn:
        out.append({"level": "warning", "code": "RES-MESH-ENTRY-NAME", "message": f"material entry names repeat: {', '.join(dupn[:6])}"})
    apps = []
    seen_apps = Counter()
    for a in rc.get("appearances") or []:
        d = a.get("Data") or {}
        an = cname(d.get("name"))
        seen_apps[an] += 1
        cm = [cname(x) for x in d.get("chunkMaterials") or []]
        apps.append(an)
        if chunks is not None and len(cm) != len(chunks):
            out.append({"level": "error", "code": "RES-MESH-CHUNKMATS",
                        "message": f"appearance '{an}' maps {len(cm)} chunk materials, the mesh has {len(chunks)} submeshes"})
        missing = sorted({m for m in cm if m not in names})
        if missing:
            out.append({"level": "error", "code": "RES-MESH-MATNAME",
                        "message": f"appearance '{an}' uses materials with no entry: {', '.join(missing[:6])}"})
    for an, n in seen_apps.items():
        if n > 1:
            out.append({"level": "warning", "code": "RES-MESH-APP-DUP", "message": f"appearance name '{an}' appears {n} times"})
    if chunks is None:
        out.append({"level": "warning", "code": "RES-MESH-NO-BLOB", "message": "no renderResourceBlob header: submesh count unknown"})
    summary = {"submeshes": len(chunks) if chunks is not None else None,
               "lods": sorted({c.get("lodMask") for c in chunks or []}),
               "material_entries": len(entries), "local_instances": n_local, "external_materials": n_ext,
               "material_storage": "preloadLocalMaterialInstances" if rc.get("preloadLocalMaterialInstances") else
               ("localMaterialBuffer" if n_local else "external"),
               "appearances": apps, "skinned_bones": len(rc.get("boneNames") or []),
               "shadow_mesh": bool(rc.get("isShadowMesh"))}
    return out, summary


def _components_vs_chunks(owner: str, comps: list, chunks: list[dict]) -> list[dict]:
    names_c = sorted(filter(None, (cname(c.get("name")) for c in comps or [] if isinstance(c, dict))))
    names_k = sorted(filter(None, (cname(c.get("name")) for c in chunks)))
    if comps and names_c != names_k:
        only_c = sorted(set(names_c) - set(names_k))[:6]
        only_k = sorted(set(names_k) - set(names_c))[:6]
        return [{"level": "warning", "code": "RES-COMPONENTS-CHUNKS",
                 "message": f"{owner}: 'components' and compiledData chunks differ (only in components: {only_c}; only in "
                            f"chunks: {only_k}). The game reads the chunks."}]
    return []


def app_check(rc: dict, index: dict) -> tuple[list[dict], dict]:
    out = []
    apps = []
    for a in rc.get("appearances") or []:
        d = resolve(a, index) or {}
        an = cname(d.get("name"))
        chunks = _chunks(d.get("compiledData"))
        out += _cruid_check(f"appearance '{an}'", d.get("compiledData"))
        out += _components_vs_chunks(f"appearance '{an}'", d.get("components"), chunks)
        comps = [_component(c, index) for c in chunks]
        lights = [c for c in comps if c["type"] == "vehicleLightComponent"]
        for lc in lights:
            if not lc.get("light_type") or not lc.get("material_zone"):
                out.append({"level": "warning", "code": "RES-APP-LIGHT",
                            "message": f"appearance '{an}': light '{lc['name']}' has no lightType or materialZone"})
        proxy = cname(((d.get("proxyMesh") or {}).get("DepotPath")) or {})
        has_proxy_comp = any(c["type"] == "entAppearanceProxyMeshComponent" for c in comps)
        if proxy and proxy != "0" and not has_proxy_comp:
            out.append({"level": "warning", "code": "RES-APP-PROXY",
                        "message": f"appearance '{an}' sets proxyMesh but has no entAppearanceProxyMeshComponent"})
        apps.append({"name": an, "components": len(comps), "meshes": sorted({c["mesh"] for c in comps if c.get("mesh")}),
                     "lights": [{k: c.get(k) for k in ("name", "light_type", "material_zone", "bound_to")} for c in lights],
                     "proxy_mesh": proxy if proxy and proxy != "0" else None,
                     "types": dict(Counter(c["type"] for c in comps).most_common())})
    return out, {"appearances": len(apps), "detail": apps}


def ent_check(rc: dict, index: dict) -> tuple[list[dict], dict]:
    out = []
    chunks = _chunks(rc.get("compiledData"))
    entity = chunks[0].get("$type") if chunks else None
    comp_chunks = chunks[1:] if chunks and "Component" not in (entity or "") else chunks
    out += _cruid_check("entity", rc.get("compiledData"))
    out += _components_vs_chunks("entity", rc.get("components"), comp_chunks)
    apps = []
    for a in rc.get("appearances") or []:
        res = cname(((a.get("appearanceResource") or {}).get("DepotPath")) or {})
        apps.append({"name": cname(a.get("name")), "appearance": cname(a.get("appearanceName")), "resource": res})
        if not res or res == "0":
            out.append({"level": "error", "code": "RES-ENT-APP", "message": f"entity appearance '{cname(a.get('name'))}' has no .app"})
    comps = [_component(c, index) for c in comp_chunks]
    return out, {"entity_object": entity, "default_appearance": cname(rc.get("defaultAppearance")),
                 "appearances": apps, "components": len(comps),
                 "slots": [c["name"] for c in comps if c["type"] == "entSlotComponent"],
                 "types": dict(Counter(c["type"] for c in comps).most_common())}


# --- references --------------------------------------------------------------------

def project_root_of(path: Path) -> Path | None:
    """The archive source root (<project>/source/archive) a resource file lives under, if any."""
    for parent in Path(path).resolve().parents:
        if parent.name.lower() == "archive" and parent.parent.name.lower() == "source":
            return parent
    return None


def tree_hashes(root: Path) -> dict[int, str]:
    """hash -> archive-relative path for every file under an archive source root."""
    out = {}
    for f in root.rglob("*"):
        if f.is_file():
            relp = f.relative_to(root).as_posix()
            out[resource_hash(relp)] = relp.replace("/", "\\")
    return out


_GAME_HASHES: dict[str, dict[int, str]] = {}


def game_hashes(game_root: Path) -> dict[int, str]:
    """hash -> archive file name over the game's own and installed mods' archives (index only, cached)."""
    key = str(game_root)
    if key not in _GAME_HASHES:
        from .conflicts import archive_files
        files = archive_files(game_root) + sorted((game_root / "archive/pc/content").glob("*.archive")) + \
            sorted((game_root / "archive/pc/ep1").glob("*.archive"))
        out: dict[int, str] = {}
        for a in files:
            try:
                for h in read_archive(a, with_names=False).hashes:
                    out.setdefault(h, a.name)
            except ForgeError:
                continue
        _GAME_HASHES[key] = out
    return _GAME_HASHES[key]


def references(doc: dict) -> list[tuple[str, int]]:
    """Every non-empty ResourcePath in the document as (shown text, hash)."""
    out = []

    def fn(o, _):
        if isinstance(o, dict) and o.get("$type") == "ResourcePath":
            v = str(o.get("$value", ""))
            if not v or v == "0":
                return
            if o.get("$storage") == "uint64" or v.isdigit():
                out.append((v, int(v)))
            else:
                out.append((v, resource_hash(v)))
    _walk(doc, fn)
    seen, uniq = set(), []
    for v, h in out:
        if h not in seen:
            seen.add(h)
            uniq.append((v, h))
    return uniq


def reference_check(doc: dict, project: dict[int, str], game: dict[int, str] | None) -> tuple[list[dict], dict]:
    refs = references(doc)
    missing, in_project, in_game = [], 0, 0
    for shown, h in refs:
        if h in project:
            in_project += 1
        elif game is not None and h in game:
            in_game += 1
        else:
            missing.append(shown if not shown.isdigit() else f"hash {h:#018x}")
    # Vanilla files themselves point at a few paths that never shipped (the 2.5 Archer Hella .ent references
    # base_vehicle.aiarch and veh_brake_lights.effect), so a missing base\ or ep1\ path is listed, not warned.
    vanilla = [m for m in missing if m.lower().startswith(("base\\", "ep1\\", "engine\\"))]
    own = [m for m in missing if m not in vanilla]
    out = []
    if own and game is not None:
        out.append({"level": "warning", "code": "RES-REF-MISSING",
                    "message": f"{len(own)} referenced resource(s) are in neither this project's source/archive nor "
                               f"any game or installed archive", "missing": own[:20]})
    return out, {"references": len(refs), "in_project": in_project, "in_game": in_game,
                 "unresolved": len(own) if game is not None else None,
                 "vanilla_paths_not_shipped": vanilla[:20] if game is not None else None}


def name_hashes(doc: dict, names: dict[int, str]) -> None:
    """Show project paths instead of bare hashes in uint64-stored ResourcePaths (in place, for summaries)."""
    def fn(o, _):
        if isinstance(o, dict) and o.get("$type") == "ResourcePath" and str(o.get("$value", "")).isdigit():
            h = int(o["$value"])
            if h in names:
                o["$value"] = names[h]
    _walk(doc, fn)


def check(doc: dict) -> dict:
    rc = (doc.get("Data") or {}).get("RootChunk") or {}
    rtype = rc.get("$type")
    index = handle_index(doc)
    findings = generic_checks(doc)
    summary: dict = {}
    if rtype == "CMesh":
        f, summary = mesh_check(rc)
        findings += f
    elif rtype == "appearanceAppearanceResource":
        f, summary = app_check(rc, index)
        findings += f
    elif rtype == "entEntityTemplate":
        f, summary = ent_check(rc, index)
        findings += f
    errors = [x for x in findings if x.get("level") == "error"]
    warnings = [x for x in findings if x.get("level") == "warning"]
    for x in errors + warnings:
        x.pop("level", None)
    return {"type": rtype, "ok": not errors, "errors": errors, "warnings": warnings, "summary": summary,
            "wolvenkit": (doc.get("Header") or {}).get("WolvenKitVersion")}
