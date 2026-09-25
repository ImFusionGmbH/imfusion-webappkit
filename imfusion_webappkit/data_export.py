"""Server-side export helpers for browser downloads."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
import tempfile
from typing import Any, Optional, Sequence, Union
import zipfile

import imfusion
import numpy as np


class ExportFormat(str, Enum):
    """Browser-download export format for session data."""

    IMF = "imf"
    NIFTI = "nii.gz"
    DICOM = "dicom"

    @classmethod
    def _missing_(cls, value: object) -> Optional["ExportFormat"]:
        if not isinstance(value, str):
            return None
        normalized = value.lower().strip().lstrip(".")
        aliases = {
            "nii": cls.NIFTI,
            "nifti": cls.NIFTI,
            "nifti.gz": cls.NIFTI,
            "dcm": cls.DICOM,
        }
        if normalized in aliases:
            return aliases[normalized]
        for member in cls:
            if member.value == normalized:
                return member
        return None


SUPPORTED_EXPORT_FORMATS = tuple(ExportFormat)


@dataclass(frozen=True)
class ExportArtifact:
    """A file ready to be transferred to the browser."""

    filename: str
    media_type: str
    content: bytes


def _safe_stem(name: str, fallback: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return stem or fallback


def _read(path: Path) -> bytes:
    with path.open("rb") as stream:
        return stream.read()


def _require_nonempty_file(path: Path, export_format: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"{export_format} export did not produce a valid file")


def _validate_dicom_input(item: Any, name: str) -> None:
    if not isinstance(item, imfusion.SharedImageSet):
        raise ValueError(
            f"DICOM export only supports image datasets; {name!r} is not an image"
        )
    if any(np.asarray(image).dtype.kind == "f" for image in item):
        raise ValueError(
            f"DICOM export does not support floating-point pixel data in {name!r}. "
            "Convert the image to an integer pixel type before exporting."
        )


def _validate_saved_dicom(path: Path) -> None:
    """Catch DICOM writer failures that are only reported through native logs."""
    _require_nonempty_file(path, "DICOM")
    try:
        loaded = imfusion.io.load(path)
    except Exception as exc:
        raise RuntimeError(f"DICOM export produced an invalid file: {exc}") from exc
    if not loaded:
        raise RuntimeError("DICOM export produced a file containing no image data")


def _zip_files(files: Sequence[Path], archive_path: Path) -> bytes:
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.name)
    return _read(archive_path)


def export_data(
    data: Sequence[Any],
    names: Sequence[str],
    export_format: Union[str, ExportFormat],
) -> ExportArtifact:
    """Export session data to IMF, NIfTI, or DICOM.

    Formats that only represent one dataset per file are returned as a ZIP when
    more than one dataset is exported.
    """
    if not data:
        raise ValueError("At least one dataset is required for export")
    export_format = ExportFormat(export_format)

    with tempfile.TemporaryDirectory(prefix="imfusion-web-export-") as directory:
        root = Path(directory)
        if export_format == "imf":
            output = root / "export.imf"
            imfusion.io.save(list(data), output)
            return ExportArtifact(
                output.name, "application/octet-stream", _read(output)
            )

        suffix = ".nii.gz" if export_format == "nii.gz" else ".dcm"
        outputs = []
        used_names: set[str] = set()
        for index, item in enumerate(data):
            base = _safe_stem(
                names[index] if index < len(names) else "",
                f"data-{index + 1}",
            )
            unique = base
            counter = 2
            while unique.lower() in used_names:
                unique = f"{base}-{counter}"
                counter += 1
            used_names.add(unique.lower())
            output = root / f"{unique}{suffix}"
            if export_format == "nii.gz":
                imfusion.io.save(item, output)
                _require_nonempty_file(output, "NIfTI")
            else:
                _validate_dicom_input(
                    item, names[index] if index < len(names) else unique
                )
                imfusion.algorithm.execute(
                    "DICOM.DicomIOAlgorithmFile",
                    [item],
                    {"location": str(output)},
                )
                _validate_saved_dicom(output)
            outputs.append(output)

        if len(outputs) == 1:
            media_type = (
                "application/gzip" if export_format == "nii.gz" else "application/dicom"
            )
            return ExportArtifact(outputs[0].name, media_type, _read(outputs[0]))

        archive = root / f"export-{export_format.replace('.', '-')}.zip"
        return ExportArtifact(
            archive.name,
            "application/zip",
            _zip_files(outputs, archive),
        )
