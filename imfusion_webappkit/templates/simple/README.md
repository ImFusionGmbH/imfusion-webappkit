# {{PROJECT_TITLE}}

An interactive medical-imaging algorithm demo built with ImFusion WebAppKit.

## Run

Verify the ImFusion SDK, licenses, OpenGL context, frontend bundle, and default
port:

```bash
uv run imfusion-webappkit doctor
```

Start the application:

```bash
uv run python app.py
```

Then open <http://127.0.0.1:8000>.

The starter action creates an aligned label map by applying a browser-editable
intensity threshold to the loaded image.

## Customize

- Replace `process_image()` in `algorithm.py` with your method.
- Edit the parameters passed to `webapp.register()` in `app.py`.
- Change `ThemePreset` in `app.py` (`DARK`, `GRAY`, or `LIGHT`).
- Replace the About text with your method description, citation, and contact.
- Add a small, redistributable sample dataset if appropriate.
