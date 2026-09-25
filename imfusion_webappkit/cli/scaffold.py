"""Project scaffolding for the `init` command."""

from __future__ import annotations

from importlib import resources
import json
from pathlib import Path
import re
import sys
from typing import Optional

from imfusion_webappkit.config import ThemePreset

from ._constants import AVAILABLE_TEMPLATES


def _project_name(destination: Path) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", destination.name.lower()).strip("-")
    if not normalized:
        raise ValueError("Could not derive a project name from the destination")
    return normalized


def _webappkit_source_line() -> str:
    """Reference the repository when the CLI is running from a source checkout."""
    source_root = Path(__file__).resolve().parent.parent.parent
    pyproject = source_root / "pyproject.toml"
    if not pyproject.is_file():
        return ""
    contents = pyproject.read_text(encoding="utf-8")
    if not re.search(
        r'(?m)^name\s*=\s*["\']imfusion-webappkit["\']\s*$',
        contents,
    ):
        return ""
    source_path = json.dumps(source_root.as_posix())
    return f"imfusion-webappkit = {{ path = {source_path}, editable = true }}"


def _template_files(root, prefix: Path = Path()) -> list[tuple[object, Path]]:
    """Return all files below a template resource and their relative paths."""
    files = []
    for item in sorted(root.iterdir(), key=lambda child: child.name):
        relative_path = prefix / item.name
        if item.is_file():
            files.append((item, relative_path))
        elif item.is_dir():
            files.extend(_template_files(item, relative_path))
    return files


def _agent_compatible_files(
    template_files: list[tuple[object, Path]],
) -> list[tuple[object, Path]]:
    """Install Cursor skills in Claude Code's project skill directory too."""
    compatible_files = []
    for resource, relative_path in template_files:
        compatible_files.append((resource, relative_path))
        if relative_path.parts[:2] == (".cursor", "skills"):
            compatible_files.append(
                (resource, Path(".claude", *relative_path.parts[1:]))
            )
    return compatible_files


def _theme_preset(theme: Optional[str]) -> ThemePreset:
    if theme is None:
        return ThemePreset.DARK
    try:
        return ThemePreset(theme)
    except (TypeError, ValueError) as exc:
        expected = ", ".join(f"'{preset.value}'" for preset in ThemePreset)
        raise ValueError(
            f"Unknown theme preset {theme!r}; choose from {expected}"
        ) from exc


def scaffold_project(
    destination: Path,
    *,
    template: str = "simple",
    title: Optional[str] = None,
    theme: Optional[str] = None,
    force: bool = False,
) -> list[Path]:
    """Copy a bundled application template into a destination directory."""
    if template not in AVAILABLE_TEMPLATES:
        raise ValueError(
            f"Unknown template {template!r}; choose from {AVAILABLE_TEMPLATES!r}"
        )
    destination = destination.expanduser().resolve()
    project_name = _project_name(destination)
    project_title = (
        title or destination.name.replace("-", " ").replace("_", " ").title()
    )
    theme_preset = _theme_preset(theme)
    templates_root = resources.files("imfusion_webappkit").joinpath("templates")
    template_files = _agent_compatible_files(
        [
            *_template_files(templates_root.joinpath("_shared")),
            *_template_files(templates_root.joinpath(template)),
        ]
    )
    conflicts = [
        destination / relative_path
        for _, relative_path in template_files
        if (destination / relative_path).exists()
    ]
    if conflicts and not force:
        listed = ", ".join(
            path.relative_to(destination).as_posix() for path in conflicts
        )
        raise FileExistsError(
            f"Refusing to overwrite existing template files: {listed}. Use --force."
        )

    destination.mkdir(parents=True, exist_ok=True)
    replacements = {
        "{{PROJECT_NAME}}": project_name,
        "{{PROJECT_TITLE}}": project_title,
        "{{THEME_PRESET}}": theme_preset.name,
        # Commented out in the template so that each pyproject.toml stays valid
        # TOML, which anything scanning the repository will try to parse, and
        # the marker carries the comment so rendering replaces the whole line.
        "# {{WEBAPPKIT_SOURCE_LINE}}": _webappkit_source_line(),
    }
    written = []
    for template_file, relative_path in template_files:
        content = template_file.read_text(encoding="utf-8")
        for placeholder, value in replacements.items():
            content = content.replace(placeholder, value)
        output = destination / relative_path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        written.append(output)
    return written


def scaffold_simple_project(
    destination: Path,
    *,
    title: Optional[str] = None,
    theme: Optional[str] = None,
    force: bool = False,
) -> list[Path]:
    """Create the default simple project."""
    return scaffold_project(
        destination,
        template="simple",
        title=title,
        theme=theme,
        force=force,
    )


def run_init(
    destination: Path,
    *,
    template: str,
    title: Optional[str],
    theme: Optional[str],
    force: bool,
) -> int:
    """Create an application starter project."""
    try:
        written = scaffold_project(
            destination,
            template=template,
            title=title,
            theme=theme,
            force=force,
        )
    except (FileExistsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    root = destination.expanduser().resolve()
    print(f"Created {template} WebAppKit project in {root}")
    for path in written:
        print(f"  {path.relative_to(root).as_posix()}")
    print()
    print("Next steps:")
    print(f"  cd {root}")
    print("  uv sync")
    print("  uv run python app.py")
    return 0
