"""Let the suite run on a machine that has the SDK but no license.

The ImFusion Python SDK installs from a public index, so any runner can import
it, but a license activates the parts of it that actually process data. A fork,
a pull request from outside the organization, and a contributor's laptop will
not have one, and the tests that need it should say so rather than fail.

Two guards do that. A test known to need a license carries the
`requires_license` marker and is skipped up front. Everything else is watched
as it runs: a failure that names a missing license is turned into a skip, which
covers both the in-process `MissingLicenseError` and the tests that assert on
the log of an application they started as a subprocess. Set
`IMFUSION_WEBAPPKIT_REQUIRE_LICENSE=1` where a license is expected — CI does
this whenever the secret is configured — and both guards step aside, so a
broken activation is reported as the failure it is instead of disappearing.
"""

import functools
import os

import pytest

# Matched against the text of a failure, so this has to cover what the SDK
# raises in this process and what it writes to the log of one we started.
_LICENSE_FAILURES = (
    "missinglicenseerror",
    "missing license",
    "no valid license",
    "not licensed",
    "license is required",
    "license required",
)

_SKIP_REASON = "Needs an activated ImFusion license"


@functools.cache
def license_is_active() -> bool:
    """Report whether the SDK in this interpreter found a license."""
    try:
        import imfusion

        return bool(imfusion.info().license.key)
    except Exception:  # noqa: BLE001 - any failure here means "cannot tell, assume not"
        return False


@functools.cache
def _license_is_mandatory() -> bool:
    return os.environ.get("IMFUSION_WEBAPPKIT_REQUIRE_LICENSE", "") not in ("", "0")


def _blames_the_license(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _LICENSE_FAILURES)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_license: needs an activated ImFusion license to do anything useful",
    )


def pytest_collection_modifyitems(config, items):
    if _license_is_mandatory() or not any(
        "requires_license" in item.keywords for item in items
    ):
        return
    if license_is_active():
        return
    skip = pytest.mark.skip(reason=_SKIP_REASON)
    for item in items:
        if "requires_license" in item.keywords:
            item.add_marker(skip)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if (
        report.failed
        and call.excinfo is not None
        and not _license_is_mandatory()
        and _blames_the_license(str(call.excinfo.value))
        and not license_is_active()
    ):
        report.outcome = "skipped"
        report.longrepr = (item.location[0], item.location[1] or 0, _SKIP_REASON)
    return report
