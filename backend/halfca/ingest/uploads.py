"""Sort a bag of uploaded files (a dropped folder, loose files or a zip) into sources.

Each CSV/XML/JSON is recognised by name first and content second (csv_loader.detect_kind).
PDFs and images are kept for AI extraction; anything else is ignored and reported.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .csv_loader import detect_kind

DATA_SUFFIXES = {".csv", ".xml", ".json"}
DOC_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
MAX_ZIP_ENTRIES = 3_000
MAX_ZIP_BYTES = 150 * 1024 * 1024


class UploadError(ValueError):
    """A problem the user can fix (shown verbatim in the Upload screen)."""


@dataclass
class Collected:
    sources: dict[str, Path] = field(default_factory=dict)  # kind -> file
    documents: list[Path] = field(default_factory=list)  # invoice PDFs / images
    ignored: list[str] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)  # file name -> note


def safe_name(name: str) -> str:
    """Last path component, with anything odd replaced (folder drops send relative paths)."""
    base = Path(name.replace("\\", "/")).name
    base = re.sub(r"[^\w.\- ()–]", "_", base).strip(" .")
    return base or "file"


def _unzip(path: Path, into: Path) -> list[Path]:
    out: list[Path] = []
    total = 0
    with zipfile.ZipFile(path) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_ZIP_ENTRIES:
            raise UploadError(f"{path.name} has too many files ({len(infos)})")
        for info in infos:
            total += info.file_size
            if total > MAX_ZIP_BYTES:
                raise UploadError(f"{path.name} expands to more than 150 MB")
            name = safe_name(info.filename)
            if name.startswith(".") or "__MACOSX" in info.filename:
                continue
            target = into / f"{len(out):04d}-{name}"
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            out.append(target)
    return out


def collect(paths: list[Path], workdir: Path) -> Collected:
    c = Collected()
    queue = list(paths)
    unzip_dir = workdir / "unzipped"
    while queue:
        p = queue.pop(0)
        suffix = p.suffix.lower()
        shown = p.name.split("-", 1)[1] if p.parent == unzip_dir and "-" in p.name else p.name
        if suffix == ".zip":
            unzip_dir.mkdir(parents=True, exist_ok=True)
            queue.extend(_unzip(p, unzip_dir))
            continue
        if suffix in DOC_SUFFIXES:
            c.documents.append(p)
            continue
        if suffix not in DATA_SUFFIXES or shown.startswith("."):
            c.ignored.append(shown)
            continue
        head = p.read_text(errors="ignore")[:400]
        kind = detect_kind(shown, head)
        if kind is None:
            c.ignored.append(shown)
            c.notes[shown] = "Not recognised as invoices, bank, Tally, IMS or e-way bill data"
        elif kind in c.sources:
            c.ignored.append(shown)
            c.notes[shown] = f"A second {kind} file; using {c.sources[kind].name}"
        else:
            c.sources[kind] = p
    return c
