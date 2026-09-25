"""Configuration types for :class:`ImFusionWebApp`."""

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Sequence, Union


class ThemePreset(str, Enum):
    """Built-in application theme."""

    DARK = "dark"
    GRAY = "gray"
    LIGHT = "light"


class TitlePosition(str, Enum):
    """Horizontal position of the application title."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class SidePosition(str, Enum):
    """Side of the application occupied by a panel or logo."""

    LEFT = "left"
    RIGHT = "right"


class ViewLayout(str, Enum):
    """Initial Web SDK viewer arrangement."""

    AUTO = "Auto"
    ROWS = "Rows"
    FOCUS_PLUS_STACK = "FocusPlusStack"
    FOCUS_PLUS_ROWS = "FocusPlusRows"


class ViewType(str, Enum):
    """Web SDK view that can be shown initially."""

    TWO_D = "2d"
    MPR = "mpr"
    AXIAL = "axial"
    CORONAL = "coronal"
    SAGITTAL = "sagittal"
    THREE_D = "3d"


@dataclass
class SampleDataset:
    """Dataset offered as a shortcut on the application's landing page.

    Args:
        name: Label displayed on the dataset card.
        path: Local dataset file loaded when the card is selected.
        thumbnail: Optional local preview image. When omitted, the card displays
            the dataset name in its center.
    """

    name: str
    path: Union[str, Path]
    thumbnail: Optional[Union[str, Path]] = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("sample dataset name must not be empty")


@dataclass
class SidebarConfig:
    """Configuration for sidebar panel visibility.

    Attributes:
        show_datamodel: Whether to show the Data Model panel. Defaults to True.
        show_views: Whether to show the Views panel. Defaults to True.
        show_display_options: Whether to show the Display Options panel. Defaults to True.
        show_annotations: Whether to show the Annotations panel, which lets the
            user place and delete annotations on the selected dataset. Defaults
            to False, since most applications drive annotations from a workflow
            step or an action parameter instead.
        collapsed: Whether the sidebar is collapsed by default. Defaults to False.

    Note:
        Configure the Algorithms panel with ImFusionWebApp(algorithm_selector=...).
    """

    show_datamodel: bool = True
    show_views: bool = True
    show_display_options: bool = True
    show_annotations: bool = False
    collapsed: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class BrandingConfig:
    """Application branding shown in the browser client.

    Logo and favicon paths may be absolute or relative to the process working
    directory. They are served by the application rather than copied into the
    package's static files.
    """

    logo: Optional[Union[str, Path]] = None
    favicon: Optional[Union[str, Path]] = None
    landing_page_title: Optional[str] = None
    landing_page_message: Optional[str] = None

    def __post_init__(self) -> None:
        self.logo = self._resolve_asset("logo", self.logo)
        self.favicon = self._resolve_asset("favicon", self.favicon)

    @staticmethod
    def _resolve_asset(name: str, value: Optional[Union[str, Path]]) -> Optional[Path]:
        if value is None:
            return None
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Branding {name} file does not exist: {path}")
        return path


@dataclass
class InfoConfig:
    """Generic information dialog shown from the application header.

    Content is rendered as Markdown by the browser client.
    """

    content: str
    title: str = "About"
    button_label: str = "About"

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("info content must not be empty")
        if not self.title.strip():
            raise ValueError("info title must not be empty")
        if not self.button_label.strip():
            raise ValueError("info button_label must not be empty")

    def to_dict(self) -> dict:
        """Convert to browser configuration."""
        return asdict(self)


@dataclass
class ThemeConfig:
    """Visual theme preset with optional semantic token overrides."""

    preset: ThemePreset = ThemePreset.DARK
    primary: Optional[str] = None
    primary_hover: Optional[str] = None
    secondary: Optional[str] = None
    background: Optional[str] = None
    surface: Optional[str] = None
    surface_raised: Optional[str] = None
    surface_high: Optional[str] = None
    text: Optional[str] = None
    text_muted: Optional[str] = None
    text_subtle: Optional[str] = None
    on_primary: Optional[str] = None
    border: Optional[str] = None
    success: Optional[str] = None
    danger: Optional[str] = None
    warning: Optional[str] = None
    info: Optional[str] = None
    font_family: Optional[str] = None

    def __post_init__(self) -> None:
        try:
            self.preset = ThemePreset(self.preset)
        except (TypeError, ValueError) as exc:
            expected = ", ".join(f"'{preset.value}'" for preset in ThemePreset)
            raise ValueError(
                f"Unknown theme preset '{self.preset}'. Expected one of {expected}."
            ) from exc

    def to_dict(self) -> dict:
        """Convert to browser configuration."""
        config = asdict(self)
        config["preset"] = self.preset.value
        return config


@dataclass
class LayoutConfig:
    """Page layout and initial viewer arrangement.

    When a panel is resizable, its configured width is the initial width only:
    the panel edge can be dragged in the browser to resize it within the same
    180 to 640 pixel range.
    """

    header_title_position: TitlePosition = TitlePosition.LEFT
    header_logo_position: SidePosition = SidePosition.LEFT
    sidebar_position: SidePosition = SidePosition.LEFT
    sidebar_width: int = 320
    sidebar_resizable: bool = True
    workflow_panel_position: SidePosition = SidePosition.LEFT
    workflow_panel_width: int = 320
    workflow_panel_resizable: bool = True
    show_status_bar: bool = True
    initial_view_layout: Optional[ViewLayout] = None
    initial_visible_views: Optional[Union[ViewType, Sequence[ViewType]]] = None

    def __post_init__(self) -> None:
        try:
            self.header_title_position = TitlePosition(self.header_title_position)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "header_title_position must be 'left', 'center', or 'right'"
            ) from exc
        for field_name in (
            "header_logo_position",
            "sidebar_position",
            "workflow_panel_position",
        ):
            try:
                setattr(self, field_name, SidePosition(getattr(self, field_name)))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{field_name} must be either 'left' or 'right'"
                ) from exc
        if (
            isinstance(self.sidebar_width, bool)
            or not isinstance(self.sidebar_width, int)
            or not 180 <= self.sidebar_width <= 640
        ):
            raise ValueError("sidebar_width must be an integer from 180 to 640")
        if (
            isinstance(self.workflow_panel_width, bool)
            or not isinstance(self.workflow_panel_width, int)
            or not 180 <= self.workflow_panel_width <= 640
        ):
            raise ValueError("workflow_panel_width must be an integer from 180 to 640")
        for field_name in ("sidebar_resizable", "workflow_panel_resizable"):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be a boolean")
        if self.initial_view_layout is not None:
            try:
                self.initial_view_layout = ViewLayout(self.initial_view_layout)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "initial_view_layout must be Auto, Rows, FocusPlusStack, "
                    "FocusPlusRows, or None"
                ) from exc
        if self.initial_visible_views is not None:
            if isinstance(self.initial_visible_views, str):
                views = (self.initial_visible_views,)
            else:
                views = tuple(self.initial_visible_views)
            try:
                self.initial_visible_views = tuple(ViewType(view) for view in views)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "initial_visible_views entries must be '2d', 'mpr', 'axial', "
                    "'coronal', 'sagittal', or '3d'"
                ) from exc

    def to_dict(self) -> dict:
        """Convert to browser configuration."""
        config = asdict(self)
        config["header_title_position"] = self.header_title_position.value
        config["header_logo_position"] = self.header_logo_position.value
        config["sidebar_position"] = self.sidebar_position.value
        config["workflow_panel_position"] = self.workflow_panel_position.value
        config["initial_view_layout"] = (
            self.initial_view_layout.value if self.initial_view_layout else None
        )
        config["initial_visible_views"] = (
            tuple(view.value for view in self.initial_visible_views)
            if self.initial_visible_views is not None
            else None
        )
        return config
