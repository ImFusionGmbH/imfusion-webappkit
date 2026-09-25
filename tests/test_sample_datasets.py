import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from imfusion_webappkit import ImFusionWebApp, SampleDataset


def route_endpoint(webapp, path):
    return next(
        route.endpoint
        for route in webapp._fastapi_app.routes
        if getattr(route, "path", None) == path
    )


def test_sample_datasets_are_exposed_with_optional_thumbnails(tmp_path):
    data = tmp_path / "scan.nii.gz"
    thumbnail = tmp_path / "scan.png"
    data.write_bytes(b"scan")
    thumbnail.write_bytes(b"preview")
    webapp = ImFusionWebApp(
        sample_datasets=[
            SampleDataset("Previewed scan", data, thumbnail),
            SampleDataset("Text-only scan", data),
        ]
    )

    config = asyncio.run(route_endpoint(webapp, "/config")())

    assert config["sample_datasets"] == [
        {
            "name": "Previewed scan",
            "data_url": "/sample-datasets/0/data/scan.nii.gz",
            "thumbnail_url": "/sample-datasets/0/thumbnail/scan.png",
        },
        {
            "name": "Text-only scan",
            "data_url": "/sample-datasets/1/data/scan.nii.gz",
            "thumbnail_url": None,
        },
    ]


def test_sample_dataset_route_serves_data_and_thumbnail(tmp_path):
    data = tmp_path / "scan.imf"
    thumbnail = tmp_path / "preview.jpg"
    data.write_bytes(b"scan")
    thumbnail.write_bytes(b"preview")
    webapp = ImFusionWebApp(sample_datasets=[SampleDataset("Scan", data, thumbnail)])
    endpoint = route_endpoint(
        webapp, "/sample-datasets/{dataset_index}/{asset_type}/{filename}"
    )

    data_response = asyncio.run(endpoint(0, "data", "scan.imf"))
    thumbnail_response = asyncio.run(endpoint(0, "thumbnail", "preview.jpg"))

    assert isinstance(data_response, FileResponse)
    assert Path(data_response.path) == data.resolve()
    assert Path(thumbnail_response.path) == thumbnail.resolve()
    with pytest.raises(HTTPException, match="asset not found"):
        asyncio.run(endpoint(0, "thumbnail", "wrong.jpg"))


@pytest.mark.parametrize(
    ("dataset", "message"),
    [
        (SampleDataset("Missing data", "missing.imf"), "file does not exist"),
        (
            SampleDataset("Missing thumbnail", __file__, "missing.png"),
            "thumbnail does not exist",
        ),
    ],
)
def test_missing_sample_dataset_assets_fail_fast(dataset, message):
    with pytest.raises(FileNotFoundError, match=message):
        ImFusionWebApp(sample_datasets=[dataset])


def test_sample_dataset_rejects_blank_name():
    with pytest.raises(ValueError, match="name"):
        SampleDataset(" ", __file__)
