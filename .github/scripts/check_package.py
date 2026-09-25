"""Fail the build if a distribution is missing something a plain install needs.

The wheel carries files that no test in this repository can miss: the compiled
browser client, the scaffolding templates and their agent guidance, and the
sample dataset the demo loads. All of them arrive through `package-data` globs
in `pyproject.toml`, which fail quietly — a renamed directory or a pattern that
stops matching produces a wheel that builds, installs, imports, and then serves
nothing. Checking the archive itself is the only place that shows up before a
user sees it.
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

TEMPLATES = ("chat", "monai", "simple", "workflow")


def _requirements(names: list[str]) -> dict[str, bool]:
    def present(*fragments: str) -> bool:
        return any(all(fragment in name for fragment in fragments) for name in names)

    required = {
        "client entry point": present("/static/dist/index.html"),
        "client bundle": present("/static/dist/assets/", ".js"),
        "WebAssembly runtime": present("/static/dist/assets/", ".wasm"),
        "client icons": present("/static/dist/icons/"),
        "sample dataset": present("/examples/sample_image.nii.gz"),
        "sample thumbnail": present("/examples/sample_image_thumbnail.png"),
        "shared agent guidance": present("/templates/_shared/AGENTS.md"),
        "shared agent skill": present("/templates/_shared/.cursor/skills/"),
    }
    for template in TEMPLATES:
        required[f"{template} template"] = present(f"/templates/{template}/app.py")
        required[f"{template} project file"] = present(
            f"/templates/{template}/pyproject.toml"
        )
    return required


def _names(distribution: Path) -> list[str]:
    if distribution.suffix == ".whl":
        with zipfile.ZipFile(distribution) as archive:
            return archive.namelist()
    with tarfile.open(distribution) as archive:
        return archive.getnames()


def main() -> int:
    distributions = sorted(Path("dist").glob("*.whl")) + sorted(
        Path("dist").glob("*.tar.gz")
    )
    if not distributions:
        print("No distributions found in dist/", file=sys.stderr)
        return 1

    failed = False
    for distribution in distributions:
        # Leading separator, so a fragment cannot match the archive's own root.
        names = ["/" + name.lstrip("/") for name in _names(distribution)]
        missing = [kind for kind, ok in _requirements(names).items() if not ok]
        print(f"{distribution.name}: {len(names)} files")
        if missing:
            print(
                f"{distribution.name} is missing {', '.join(missing)}", file=sys.stderr
            )
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
