"""Tests for browser download export generation."""

from io import BytesIO
from pathlib import Path
import zipfile

import imfusion
import numpy as np
import pytest

from imfusion_webappkit.data_export import export_data, ExportFormat


def test_export_format_aliases_are_normalized():
    assert ExportFormat("NIfTI") is ExportFormat.NIFTI
    assert ExportFormat(".dcm") is ExportFormat.DICOM

    with pytest.raises(ValueError, match="is not a valid ExportFormat"):
        ExportFormat("png")


def test_multiple_nifti_datasets_are_zipped(monkeypatch):
    def save(item, path):
        Path(path).write_bytes(str(item).encode())

    monkeypatch.setattr("imfusion_webappkit.data_export.imfusion.io.save", save)

    artifact = export_data(["first", "second"], ["CT / Scan", "CT / Scan"], "nifti")

    assert artifact.filename == "export-nii-gz.zip"
    assert artifact.media_type == "application/zip"
    with zipfile.ZipFile(BytesIO(artifact.content)) as archive:
        assert archive.namelist() == ["CT_Scan.nii.gz", "CT_Scan-2.nii.gz"]


def test_single_dicom_dataset_is_returned_directly(monkeypatch):
    image = imfusion.SharedImageSet(np.zeros((1, 4, 4, 1), dtype=np.uint16))

    def execute(algorithm, data, properties):
        assert algorithm == "DICOM.DicomIOAlgorithmFile"
        assert data[0] is image
        Path(properties["location"]).write_bytes(b"DICOM")
        return []

    monkeypatch.setattr(
        "imfusion_webappkit.data_export.imfusion.algorithm.execute",
        execute,
    )
    monkeypatch.setattr(
        "imfusion_webappkit.data_export.imfusion.io.load",
        lambda _path: [object()],
    )

    artifact = export_data([image], ["Ultrasound"], "dicom")

    assert artifact.filename == "Ultrasound.dcm"
    assert artifact.media_type == "application/dicom"
    assert artifact.content == b"DICOM"


def test_float_dicom_export_fails_before_creating_an_invalid_file(monkeypatch):
    image = imfusion.SharedImageSet(np.zeros((1, 4, 4, 1), dtype=np.float32))
    monkeypatch.setattr(
        "imfusion_webappkit.data_export.imfusion.algorithm.execute",
        lambda *_args, **_kwargs: pytest.fail("DICOM writer should not run"),
    )

    with pytest.raises(ValueError, match="does not support floating-point pixel data"):
        export_data([image], ["Probability map"], "dicom")


def test_dicom_export_rejects_a_file_that_cannot_be_loaded(monkeypatch):
    image = imfusion.SharedImageSet(np.zeros((1, 4, 4, 1), dtype=np.uint16))

    def execute(_algorithm, _data, properties):
        Path(properties["location"]).write_bytes(b"invalid")
        return []

    monkeypatch.setattr(
        "imfusion_webappkit.data_export.imfusion.algorithm.execute",
        execute,
    )
    monkeypatch.setattr(
        "imfusion_webappkit.data_export.imfusion.io.load",
        lambda _path: (_ for _ in ()).throw(RuntimeError("missing BitsAllocated")),
    )

    with pytest.raises(
        RuntimeError,
        match="DICOM export produced an invalid file: missing BitsAllocated",
    ):
        export_data([image], ["CT"], "dicom")
