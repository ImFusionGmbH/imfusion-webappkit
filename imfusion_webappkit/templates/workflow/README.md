# {{PROJECT_TITLE}}

A guided medical-imaging algorithm demo built with ImFusion WebAppKit.

## Run

Verify the environment:

```bash
uv run imfusion-webappkit doctor
```

Start the workflow:

```bash
uv run python app.py
```

Then open <http://127.0.0.1:8000>.

## Workflow

The generated application guides users through:

1. an introduction;
2. image loading;
3. algorithm configuration;
4. processing with progress;
5. smart-brush label-map correction;
6. result acceptance or rejection; and
7. export.

Customize `process_image()` in `algorithm.py`, then adjust the steps and
parameters in `app.py`. Change `ThemePreset` there (`DARK`, `GRAY`, or
`LIGHT`) if the generated chrome is not the one you want. Replace the welcome
and review text with method-specific guidance, citations, and interpretation
instructions.
