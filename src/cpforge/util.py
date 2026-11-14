"""Small shared helpers: hashing, paths, file versions, JSON output."""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import zlib
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = PKG_DIR / "knowledge"
TEMPLATES_DIR = PKG_DIR / "templates"
BS = "\\"


class ForgeError(Exception):
    """An expected failure with a named cause and a fix. Exit code 2."""

    def __init__(self, message: str, fix: str = "", code: int = 2):
        super().__init__(message)
        self.fix = fix
        self.code = code


def home_dir() -> Path:
    """Where the forge keeps caches and indexes. Never inside the game folder."""
    env = os.environ.get("CPFORGE_HOME")
    if env:
        return Path(env)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "CyberpunkForge"
    return Path.home() / ".cache" / "cyberpunk-forge"


def emit(value) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    try:
        sys.stdout.write(text + "\n")
    except UnicodeEncodeError:
        sys.stdout.write(json.dumps(value, indent=2, ensure_ascii=True, default=str) + "\n")


def load_json(path: Path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- hashes -----------------------------------------------------------------

def archive_path(path: str) -> str:
    """Normalise a resource path the way archive hashes expect it.

    Lowercase with backslash separators. Verified against installed ArchiveXL
    mods: every factory path listed in their .xl files hashed to an entry of
    the matching .archive with this rule (see knowledge/facts.json).
    """
    p = path.strip().strip('"').strip("'").replace("/", BS)
    while BS + BS in p:
        p = p.replace(BS + BS, BS)
    return p.lstrip(BS).lower()


def fnv1a64(text: str) -> int:
    h = 0xCBF29CE484222325
    for b in text.encode("utf-8"):
        h = ((h ^ b) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def resource_hash(path: str) -> int:
    return fnv1a64(archive_path(path))


def tweakdb_id(name: str) -> int:
    """TweakDBID without the tdbOffset bytes: CRC32 (zlib) | byte length << 32."""
    raw = name.encode("utf-8")
    if len(raw) > 255:
        raise ForgeError(f"TweakDB name longer than 255 bytes: {name[:40]}...")
    return zlib.crc32(raw) | (len(raw) << 32)


def murmur3_32(data: bytes, seed: int) -> int:
    c1, c2 = 0xCC9E2D51, 0x1B873593
    h = seed & 0xFFFFFFFF
    n = len(data) // 4
    for i in range(n):
        k = struct.unpack_from("<I", data, i * 4)[0]
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
        h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
        h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF
    tail = data[n * 4:]
    k = 0
    if len(tail) == 3:
        k ^= tail[2] << 16
    if len(tail) >= 2:
        k ^= tail[1] << 8
    if len(tail) >= 1:
        k ^= tail[0]
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
    h ^= len(data)
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h


RECORD_TYPE_SEED = 0x5EEDBA5E


def record_type_key(type_name: str) -> int:
    """Key stored per record in tweakdb.bin: Murmur3 of the bare type name."""
    t = type_name
    if t.startswith("gamedata"):
        t = t[len("gamedata"):]
    if t.endswith("_Record"):
        t = t[: -len("_Record")]
    return murmur3_32(t.encode("utf-8"), RECORD_TYPE_SEED)


# --- files ------------------------------------------------------------------

def file_version(path: Path) -> str | None:
    """Four-part file version from the PE version resource (Windows only)."""
    if os.name != "nt" or not path.is_file():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        ver = ctypes.WinDLL("version", use_last_error=True)
        size = ver.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(str(path), 0, size, buf):
            return None
        ptr = ctypes.c_void_p()
        length = wintypes.UINT()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)):
            return None

        class FixedInfo(ctypes.Structure):
            _fields_ = [(n, wintypes.DWORD) for n in (
                "sig", "struc", "ms", "ls", "pms", "pls", "mask", "flags", "os", "type", "sub", "dms", "dls")]

        fi = ctypes.cast(ptr, ctypes.POINTER(FixedInfo)).contents
        if fi.ms == 0 and fi.ls == 0:
            return None
        return f"{fi.ms >> 16}.{fi.ms & 0xFFFF}.{fi.ls >> 16}.{fi.ls & 0xFFFF}"
    except (OSError, AttributeError, ValueError):
        return None


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def read_text(path: Path, limit: int | None = None) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read(limit) if limit else f.read()


def iter_files(root: Path, suffixes: tuple[str, ...] | None = None):
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            if suffixes is None or name.lower().endswith(suffixes):
                yield Path(dirpath) / name
