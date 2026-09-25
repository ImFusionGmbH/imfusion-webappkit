"""Write a recorded graph and a client bundle into a publishable directory.

The result is a self-contained static site: an ``index.html`` at its root so it
can be dropped into a subdirectory or an iframe unchanged, the client bundle
beside it, and the recording under ``fixtures/``. Nothing in it is served by
Python, so every URL the configuration hands to the browser has to be rewritten
to a file that is actually there.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional

from .recorder import AppMetadata, RecordedGraph

# The client looks for this tag to decide whether to replay a recording or open
# a WebSocket, so one bundle serves both without probing for files that are
# absent in a live deployment.
MANIFEST_META_NAME = "imfusion-static-demo"

FIXTURES_DIR = "fixtures"
PAYLOAD_DIR = "payloads"
BRANDING_DIR = "branding"
SAMPLES_DIR = "sample-datasets"


def _rewrite_config(
    config: Dict[str, Any], metadata: AppMetadata, output: Path
) -> Dict[str, Any]:
    """Point the configuration at copied files instead of FastAPI routes."""
    rewritten = copy.deepcopy(config)

    branding = rewritten.get("branding") or {}
    for key, path_key in (("logo_url", "logo"), ("favicon_url", "favicon")):
        source = metadata.branding.get(path_key)
        if branding.get(key) and source:
            source_path = Path(source)
            target = output / BRANDING_DIR / f"{path_key}{source_path.suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target)
            branding[key] = f"./{BRANDING_DIR}/{target.name}"
        elif branding.get(key):
            branding[key] = None
    rewritten["branding"] = branding

    datasets = rewritten.get("sample_datasets") or []
    for index, dataset in enumerate(datasets):
        described = metadata.sample_datasets[index]
        data_path = Path(described["path"])
        target = output / SAMPLES_DIR / str(index) / data_path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(data_path, target)
        dataset["data_url"] = f"./{SAMPLES_DIR}/{index}/{data_path.name}"
        thumbnail = described.get("thumbnail")
        if dataset.get("thumbnail_url") and thumbnail:
            thumbnail_path = Path(thumbnail)
            thumbnail_target = output / SAMPLES_DIR / str(index) / thumbnail_path.name
            shutil.copy2(thumbnail_path, thumbnail_target)
            dataset["thumbnail_url"] = f"./{SAMPLES_DIR}/{index}/{thumbnail_path.name}"
        elif dataset.get("thumbnail_url"):
            dataset["thumbnail_url"] = None
    rewritten["sample_datasets"] = datasets
    return rewritten


def _manifest(
    graph: RecordedGraph, config: Dict[str, Any], notice: str
) -> Dict[str, Any]:
    return {
        "protocol_version": config.get("protocol_version"),
        "notice": notice,
        "config": config,
        "actions": graph.actions,
        "handlers": graph.handlers,
        "initial_node": graph.initial_node,
        "connect": [frame.to_dict() for frame in graph.connect_frames],
        # Node JSON is small next to the datasets, so it travels with the
        # manifest and only the payloads are fetched on demand.
        "nodes": {node_id: node.to_dict() for node_id, node in graph.nodes.items()},
    }


def _inject_manifest_reference(index: Path, title: str) -> None:
    html = index.read_text(encoding="utf-8")
    reference = (
        f'    <meta name="{MANIFEST_META_NAME}" '
        f'content="./{FIXTURES_DIR}/manifest.json" />\n'
    )
    if MANIFEST_META_NAME not in html:
        html = html.replace("</head>", f"{reference}  </head>")
    html = html.replace(
        "<title>ImFusion WebApp</title>",
        f"<title>{title}</title>",
    )
    index.write_text(html, encoding="utf-8")


def write(
    graph: RecordedGraph,
    metadata: AppMetadata,
    bundle: Path,
    output: Path,
    *,
    notice: str,
    title: Optional[str] = None,
) -> List[str]:
    """Assemble the demo at `output` and return a human-readable size report."""
    index = bundle / "index.html"
    if not index.is_file():
        raise FileNotFoundError(
            f"No built client at {index}. Build it before writing the demo."
        )

    if output.exists():
        shutil.rmtree(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle, output)

    config = _rewrite_config(graph.config, metadata, output)
    fixtures = output / FIXTURES_DIR
    fixtures.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(graph, config, notice)
    (fixtures / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    payload_dir = fixtures / PAYLOAD_DIR
    payload_dir.mkdir(parents=True, exist_ok=True)
    for digest, payload in graph.payloads.items():
        (payload_dir / f"{digest}.bin").write_bytes(payload)

    _inject_manifest_reference(
        output / "index.html",
        title or f"{config.get('title', 'ImFusion WebApp')} — recorded demo",
    )

    manifest_bytes = (fixtures / "manifest.json").stat().st_size
    total = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    return [
        f"states:   {len(graph.nodes)}",
        f"edges:    {sum(len(node.edges) for node in graph.nodes.values())}",
        f"payloads: {len(graph.payloads)} "
        f"({graph.total_payload_bytes / 1024 / 1024:.1f} MB)",
        f"manifest: {manifest_bytes / 1024:.0f} KB",
        f"total:    {total / 1024 / 1024:.1f} MB",
    ]
