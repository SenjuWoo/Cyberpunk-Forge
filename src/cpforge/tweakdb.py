"""TweakDB: record existence from tweakdb.bin, names from tweakdb*.str, mod records from YAML."""
from __future__ import annotations

import struct
from pathlib import Path

from .util import ForgeError, iter_files, rel, tweakdb_id

BIN_MAGIC = 0x0BB1DB47
STR_MAGIC = 0x0BB1DB57
LOW40 = (1 << 40) - 1


def read_bin(path: Path) -> dict[int, int]:
    """Return {TweakDBID (low 40 bits): type key} for every record in a tweakdb.bin."""
    data = Path(path).read_bytes()
    if len(data) < 32:
        raise ForgeError(f"not a tweakdb.bin: {path}")
    magic, _bv, _pv, _chk, _fo, ro, _qo, _go = struct.unpack_from("<IiiIiiii", data, 0)
    if magic != BIN_MAGIC:
        raise ForgeError(f"not a tweakdb.bin (magic {magic:#x}): {path}")
    count = struct.unpack_from("<i", data, ro)[0]
    out = {}
    base = ro + 4
    for i in range(count):
        tid, key = struct.unpack_from("<QI", data, base + i * 12)
        out[tid & LOW40] = key
    return out


def _red_string(data: bytes, pos: int) -> tuple[str, int]:
    b = data[pos]
    pos += 1
    ascii_ = bool(b & 0x80)
    length = b & 0x3F
    if b & 0x40:
        shift = 6
        while True:
            c = data[pos]
            pos += 1
            length |= (c & 0x7F) << shift
            shift += 7
            if not c & 0x80:
                break
    if ascii_:
        return data[pos:pos + length].decode("latin-1"), pos + length
    return data[pos:pos + 2 * length].decode("utf-16-le", "replace"), pos + 2 * length


def read_str(path: Path) -> dict[str, list[str]]:
    """Names from a tweakdb .str file (written by REDmod deploy)."""
    data = Path(path).read_bytes()
    magic, _ver, nrec, nflat, nq = struct.unpack_from("<IIIII", data, 0)
    if magic != STR_MAGIC:
        raise ForgeError(f"not a tweakdb .str file: {path}")
    pos = 20
    out: dict[str, list[str]] = {"records": [], "flats": [], "queries": []}
    for key, n in (("records", nrec), ("flats", nflat), ("queries", nq)):
        for _ in range(n):
            s, pos = _red_string(data, pos)
            out[key].append(s)
    return out


class TweakDB:
    """Vanilla records plus whatever installed mods add. Lazy and read-only."""

    def __init__(self, game_root: Path):
        self.root = game_root
        self._ids: dict[int, int] | None = None
        self._names: list[str] | None = None
        self.sources: list[str] = []

    @property
    def ids(self) -> dict[int, int]:
        if self._ids is None:
            self._ids = {}
            for p in (self.root / "r6/cache/tweakdb.bin", self.root / "r6/cache/tweakdb_ep1.bin"):
                if p.is_file():
                    self._ids.update(read_bin(p))
                    self.sources.append(rel(p, self.root))
        return self._ids

    def exists(self, name: str) -> bool:
        return tweakdb_id(name) in self.ids

    def type_key(self, name: str) -> int | None:
        return self.ids.get(tweakdb_id(name))

    def names(self) -> list[str]:
        """Best available record-name list: REDmod .str, else the index of .tweak sources."""
        if self._names is None:
            self._names = []
            for p in (self.root / "r6/cache/modded/tweakdb_ep1.str", self.root / "r6/cache/modded/tweakdb.str"):
                if p.is_file():
                    self._names = read_str(p)["records"]
                    self.sources.append(rel(p, self.root))
                    break
        return self._names


# --- TweakXL YAML -------------------------------------------------------------

def yaml_loader():
    try:
        import yaml
    except ImportError as e:
        raise ForgeError("PyYAML is not installed", "pip install pyyaml (Install.ps1 does this)") from e

    class Loader(yaml.SafeLoader):
        pass

    def tagged(loader, tag_suffix, node):
        if isinstance(node, yaml.SequenceNode):
            value = loader.construct_sequence(node, deep=True)
        elif isinstance(node, yaml.MappingNode):
            value = loader.construct_mapping(node, deep=True)
        else:
            value = loader.construct_scalar(node)
        return {"$tag": "!" + tag_suffix, "value": value}

    Loader.add_multi_constructor("!", tagged)
    return yaml, Loader


def parse_yaml(path: Path):
    yaml, Loader = yaml_loader()
    with open(path, encoding="utf-8-sig") as f:
        return yaml.load(f, Loader=Loader)


def yaml_records(path: Path) -> dict:
    """Split a TweakXL YAML file into new/changed records and flat edits."""
    doc = parse_yaml(path) or {}
    if not isinstance(doc, dict):
        raise ForgeError(f"{path}: top level must be a mapping of record names")
    records, flats = {}, {}
    for key, value in doc.items():
        key = str(key)
        if isinstance(value, dict) and not value.get("$tag"):
            records[key] = {"type": value.get("$type"), "base": value.get("$base"),
                            "instances": "$instances" in value, "fields": [k for k in value if not str(k).startswith("$")]}
        else:
            flats[key] = value
    return {"records": records, "flats": flats}


def installed_yaml_records(game_root: Path) -> dict[str, list[str]]:
    """Record name -> list of r6/tweaks files that define or change it."""
    out: dict[str, list[str]] = {}
    for f in iter_files(game_root / "r6/tweaks", (".yaml", ".yml")):
        try:
            recs = yaml_records(f)
        except Exception:  # a broken third-party file must not stop the scan
            continue
        for name in recs["records"]:
            out.setdefault(name, []).append(rel(f, game_root))
    return out


def references(value) -> list[str]:
    """Strings in a YAML value that look like TweakDB record names (Package.Name)."""
    out = []
    if isinstance(value, dict):
        for v in value.values():
            out += references(v)
    elif isinstance(value, list):
        for v in value:
            out += references(v)
    elif isinstance(value, str):
        v = value.strip()
        if "." in v and " " not in v and not v.startswith(("$", "LocKey", "base\\", "ep1\\")) and "\\" not in v \
                and v.split(".")[0][:1].isupper() and not v.replace(".", "").isdigit():
            out.append(v)
    return out
