# Development

This page is for changing the kit itself: the React client, the documentation,
and the packaged examples. Writing an application still starts at
[Getting started](getting-started.md).

## Prerequisites

- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/)
- Node.js 18 or newer and npm
- Access to the ImFusion Python package index
- Valid ImFusion Suite and Web SDK licenses

## Installation

Create the repository-local virtual environment and install the Python package
and development dependencies:

```bash
uv sync
```

The ImFusion package index is configured in `pyproject.toml`. After changing
Python dependencies, run `uv lock` and commit the updated `uv.lock`.

Install the React client dependencies:

```bash
cd imfusion_webappkit/static
npm ci
cd ../..
```


## Development mode

Use two terminals. Start the Python server from the repository root:

```bash
uv run python imfusion_webappkit/examples/webapp_demo.py
```

Start Vite with hot reload from another terminal:

```bash
cd imfusion_webappkit/static
npm run dev
```

Open <http://localhost:3000>. Vite proxies `/ws`, `/config`, and
`/sample-datasets` to the Python server on port 8000. Python server changes
require a restart; client code under `imfusion_webappkit/static/src` is
refreshed automatically.

## Tests

Run Python tests from the repository root:

```bash
uv run pytest
```

Run client tests from the static directory:

```bash
cd imfusion_webappkit/static
npm test
```

### Tests that need a license

The SDK installs from a public index, but a license activates the parts of it
that process data. A machine without one — a fork's CI runner, an outside
contributor's laptop — skips those tests instead of failing them:
`tests/conftest.py` skips anything marked `requires_license` up front, and
turns a failure whose text names a missing license into a skip as it runs. Set
`IMFUSION_WEBAPPKIT_REQUIRE_LICENSE=1` where a license is expected, and both
guards stand down so a broken activation is reported as a failure.

## Continuous integration

Three workflows run on GitHub Actions:

- `.github/workflows/ci.yml` runs the Python suite on 3.10 through 3.13, the
  client's own tests and build, and builds the distribution. The runner has no
  GPU and no display, so it installs Mesa and runs the suite under `xvfb`.
- `.github/workflows/pages.yml` publishes the site on every push to `master`.
- `.github/workflows/release.yml` publishes to PyPI when a `v*` tag is pushed.

CI reads the license from the `IMFUSION_LICENSE_KEY` repository secret. Runs
without it still pass, with the licensed tests skipped; see above.

## Publishing the site

GitHub Pages serves one site per repository, so the landing page and the
documentation share a deployment: the landing page at the root and the
documentation under `docs/`. `landing/src/content.ts` links to the same split,
and the workflow passes the deployed base URL to mkdocs as `SITE_URL`.

Pages needs to be enabled once, under *Settings → Pages → Build and deployment*
with the source set to *GitHub Actions*.

## Publishing to the public repository

Development happens in the internal repository, whose history carries packed
copies of licensed ImFusion SDK packages from earlier layouts. Those blobs stay
reachable from any commit that once contained them, so the public repository
gets a snapshot of the tree rather than that history, on a local `public`
branch that is never merged into `master`.

Each publication replays the current tree onto `public` as a single commit,
which `git commit-tree` builds directly and so can never conflict:

```bash
git commit-tree "master^{tree}" -p public -m "Update to $(git rev-parse --short master)"
```

That prints a commit; point the branch at it and push it as the public
`master`:

```bash
git branch -f public <printed-sha>
git push github public:master
```

The first publication has no `-p public`, which is what makes it a root commit.
Two checks are worth running before any push, since both catch a mistake that
cannot be undone once the repository is public:

```bash
git diff master public          # must be empty: the tree is a snapshot
git rev-list --objects public | grep '\.tgz$'   # must find nothing
```

Because the two histories are unrelated, nothing should ever be pulled from the
public repository into `master`. A contribution arriving there has to be applied
to `master` as a patch, with `git format-patch` or a cherry-pick from a fetched
ref, and then republished by the snapshot above.

## Releasing

Releases go to PyPI through
[trusted publishing](https://docs.pypi.org/trusted-publishers/), so no API
token is stored anywhere. Configure it once on PyPI, under the project's
publishing settings, as owner `ImFusionGmbH`, repository `imfusion-webappkit`,
workflow `release.yml`, environment `pypi`. Create a matching `pypi`
environment in the repository settings, and restrict it to tags if releases
should need an approval.

Before cutting a release, regenerate the committed assets that are derived from
the client: the compiled bundle, the [documentation screenshots](#documentation-screenshots),
the landing page images, and the [recorded demo](#the-landing-pages-recorded-demo).
One script runs every step in order, and accepts step names (`client`, `docs`,
`landing`, `demo`) to run a subset:

```bash
uv run python tools/refresh_release_assets.py
```

Review and commit the result, then raise `version` in `pyproject.toml`, commit
that too, and [publish the snapshot](#publishing-to-the-public-repository) so
the public repository holds the version being released.

Publishing a GitHub release is what triggers the upload, so the tag is created
in the public repository rather than pushed from a clone. This matters here
beyond convenience: the two histories are unrelated, and pushing a tag that
points into the internal history would drag that whole history along with it,
licensed tarballs included. Under *Releases → Draft a new release*, create the
tag `v0.4.0` against the public `master`, and publish it.

The workflow refuses to publish a release whose tag disagrees with
`pyproject.toml`, because PyPI never allows a version number to be reused. To
rehearse without publishing anything, run the workflow manually from the
*Actions* tab: it builds and checks the distributions and uploads them as an
artifact, but the publishing job only runs for a release.

## Documentation

Build the documentation with strict warning handling:

```bash
uv run mkdocs build
```

Run the documentation development server:

```bash
uv run mkdocs serve
```

Open <http://127.0.0.1:8001>. The documentation server uses a different port
from the web application's default port 8000. Source files are under `docs`.

## Documentation screenshots

The images under `docs/assets/screenshots` are generated from the bundled
example applications and, for the `template-*` scenarios, from a project
scaffolded into a temporary directory. Install the browser once, then regenerate
them:

```bash
uv run playwright install chromium
uv run python tools/generate_screenshots.py
```

Each scenario starts one example application on a free port, drives the browser
client, and overwrites its PNG files. Pass scenario names to capture a subset:

```bash
uv run python tools/generate_screenshots.py workflow theme-light
```

The viewer renders through WebGL. Add `--headed` when the headless software
renderer produces an empty viewport, and `--scale 2` for high-density images.
Regenerate the screenshots whenever the client's layout, theme, or workflow
panel changes.

The landing page under `landing` shows a few of these images at half their pixel
size, some of them cropped to a thumbnail. Capture those at double density into a
scratch directory and convert them separately, so the documentation keeps its
own single-density copies:

```bash
uv run python tools/generate_screenshots.py actions template-simple \
    template-workflow template-monai template-chat registration \
    --scale 2 --output shots2x
uv run python tools/landing_assets.py shots2x
```

The MONAI scenario runs its model, which needs that template's own dependencies
(`monai`, `torch`) available to the generator.

## The landing page's recorded demo

The application embedded in the landing page is a
[recorded static demo](guides/static-demos.md), described by
`tools/build_static_demo.py`:

```bash
uv run python tools/build_static_demo.py
uv run python tools/build_static_demo.py --poster
```

The output under `landing/public/demo` is committed, because recording needs the
licensed ImFusion SDK and a CI runner that can rebuild the landing page cannot
rebuild the demo. Re-record it whenever the client or the demo application
changes, and pass `--poster` when the change is visible in the still the page
shows before the visitor presses play.

`tests/test_static_demo_browser.py` drives the committed output in a real
browser, and skips when it has not been recorded.

## Production build

Build the client and run the Python server:

```bash
cd imfusion_webappkit/static
npm run build
cd ../..
uv run python imfusion_webappkit/examples/webapp_demo.py
```

Open <http://localhost:8000>. The server uses the generated
`imfusion_webappkit/static/dist` bundle. This directory is committed so source
checkouts can run without npm; rebuild and commit it whenever the frontend
changes.

To create distributable Python packages after building the client, run:

```bash
uv build
```

The resulting wheel and source distribution include the compiled client.
Consumers installing either artifact do not need Node.js or npm.
