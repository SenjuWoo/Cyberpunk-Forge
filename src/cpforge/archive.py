"""Read the index of a Cyberpunk 2077 .archive (RDAR). Layout: knowledge/facts.json 'archive.format'."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from .util import ForgeError, archive_path, fnv1a64

MAGIC = 0x52414452
LXRS_MAGIC = 0x4C585253
CUSTOM_DATA_OFFSET = 0xAC


@dataclass
class Archive:
    path: Path
    version: int
    file_count: int
    segment_count: int
    dependency_count: int
    file_size: int
    hashes: dict[int, int] = field(default_factory=dict)  # hash -> uncompressed size of main segment
    names: list[str] = field(default_factory=list)          # embedded name list when uncompressed
    names_note: str = ""

    def contains(self, resource_path: str) -> bool:
        return fnv1a64(archive_path(resource_path)) in self.hashes

    def summary(self) -> dict:
        return {"path": str(self.path), "version": self.version, "files": self.file_count,
                "segments": self.segment_count, "dependencies": self.dependency_count,
                "size": self.file_size, "embedded_names": len(self.names), "names_note": self.names_note}


def _read_names(f, custom_len: int) -> tuple[list[str], str]:
    if custom_len < 20:
        return [], "no embedded name list"
    f.seek(CUSTOM_DATA_OFFSET)
    head = f.read(20)
    if len(head) < 20:
        return [], "custom data truncated"
    magic, version, size, zsize, count = struct.unpack("<IIiii", head)
    if magic != LXRS_MAGIC:
        return [], "custom data is not a name list"
    if size != zsize:
        return [], f"name list ({count} names) is Oodle-compressed; not read"
    data = f.read(zsize)
    names = [n.decode("latin-1") for n in data.split(b"\0") if n][:count]
    return names, f"{len(names)} names read"


def read_archive(path: Path, with_names: bool = True) -> Archive:
    path = Path(path)
    try:
        with open(path, "rb") as f:
            head = f.read(44)
            if len(head) < 44:
                raise ForgeError(f"not an archive (too small): {path}")
            magic, version, ipos, isize, _dpos, _dsize, fsize = struct.unpack("<IIQIQIQ", head[:40])
            custom_len = struct.unpack("<I", head[40:44])[0]
            if magic != MAGIC:
                raise ForgeError(f"not an RDAR archive: {path}")
            f.seek(ipos)
            idx = f.read(28)
            if len(idx) < 28:
                raise ForgeError(f"archive index truncated: {path}")
            _fto, _fts, _crc, nfiles, nsegs, ndeps = struct.unpack("<IIQIII", idx)
            entries = f.read(56 * nfiles)
            segs = f.read(16 * nsegs)
            if len(entries) < 56 * nfiles or len(segs) < 16 * nsegs:
                raise ForgeError(f"archive index truncated: {path}")
            arc = Archive(path, version, nfiles, nsegs, ndeps, fsize)
            for i in range(nfiles):
                h, _ts, _inline, s0, _s1, _d0, _d1 = struct.unpack_from("<QqIIIII", entries, i * 56)
                size = struct.unpack_from("<I", segs, s0 * 16 + 12)[0] if s0 < nsegs else 0
                arc.hashes[h] = size
            if with_names:
                arc.names, arc.names_note = _read_names(f, custom_len)
            return arc
    except OSError as e:
        raise ForgeError(f"cannot read archive {path}: {e}") from e


def find_resource(resource_path: str, archives: list[Path]) -> list[str]:
    h = fnv1a64(archive_path(resource_path))
    hits = []
    for a in archives:
        try:
            if h in read_archive(a, with_names=False).hashes:
                hits.append(str(a))
        except ForgeError:
            continue
    return hits


def write_test_archive(path: Path, resources: dict[str, bytes]) -> None:
    """Write a minimal uncompressed RDAR file (for tests and fixtures only)."""
    body = bytearray(b"\0" * CUSTOM_DATA_OFFSET)
    entries = []
    segments = []
    for name, data in resources.items():
        off = len(body)
        body += data
        segments.append(struct.pack("<QII", off, len(data), len(data)))
        idx = len(segments) - 1
        entries.append(struct.pack("<QqIIIII", fnv1a64(archive_path(name)), 0, 1, idx, idx + 1, 0, 0) + b"\0" * 20)
    ipos = len(body)
    index = struct.pack("<IIQIII", 8, 0, 0, len(entries), len(segments), 0) + b"".join(entries) + b"".join(segments)
    total = ipos + len(index)
    header = struct.pack("<IIQIQIQ", MAGIC, 12, ipos, len(index), 0, 0, total) + struct.pack("<I", 0)
    body[: len(header)] = header
    path.write_bytes(bytes(body) + index)
