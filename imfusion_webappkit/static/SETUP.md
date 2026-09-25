# Client Setup Guide

This guide explains how to set up the client-side application for ImFusion WebAppKit.

## Prerequisites

- Node.js (v18 or higher)
- npm (comes with Node.js)

## Option 1: Development Mode (Recommended for Development)

In development mode, Vite provides hot module reloading and runs the client on port 3000.

### Setup

1. **Install dependencies**:

```bash
cd imfusion_webappkit/static
npm install
```

2. **Start the Python server** (in a separate terminal):

```bash
# From project root
uv run python imfusion_webappkit/examples/webapp_demo.py
```

3. **Start the Vite dev server**:

```bash
# In imfusion_webappkit/static directory
npm run dev
```

4. **Open browser**:

Navigate to `http://localhost:3000`

The Vite dev server will proxy WebSocket connections to the Python server on port 8000.

## Option 2: Production Mode (Bundled Client)

In production mode, the client is built into static files that the Python server serves directly.

### Setup

1. **Install dependencies**:

```bash
cd imfusion_webappkit/static
npm install
```

2. **Build the client**:

```bash
npm run build
```

This creates a `dist/` directory with bundled files.

3. **Run the Python server**:

```python
from imfusion_webappkit import ImFusionWebApp

webapp = ImFusionWebApp()  # Automatically uses dist/ if it exists

@webapp.register("My Action")
def my_action(image):
    return my_callback(image)

webapp.run()
```

4. **Open browser**:

Navigate to `http://localhost:8000`

## Troubleshooting


### "Port 3000 already in use"

Change the port in `vite.config.js`:

```javascript
server: {
  port: 3001,  // Change this
  // ...
}
```

### WebSocket connection failed in dev mode

Make sure the Python server is running on port 8000. The Vite proxy is configured to forward WebSocket requests to `localhost:8000`.

### Built files not found

If you get a warning about built client not found:
1. Run `npm run build` in the static directory
2. Verify `dist/` directory was created
3. Server will automatically use it once created

## File Structure

```
imfusion_webappkit/static/
├── index.html           # Main HTML (source)
├── client.js            # Client logic (source)
├── styles.css           # Styles (source)
├── vite.config.js       # Vite configuration
├── package.json         # NPM dependencies
├── node_modules/        # (created by npm install)
└── dist/                # (created by npm run build)
    ├── index.html
    ├── assets/
    │   ├── client-[hash].js
    │   └── styles-[hash].css
    └── ...
```

## Development Workflow

1. Make changes to `client.js`, `index.html`, or `styles.css`
2. Vite automatically reloads the browser (dev mode)
3. Test with Python server running
4. When ready, build for production: `npm run build`

## Production Deployment

For production:

1. Build the client: `npm run build`
2. Deploy the Python package with the `dist/` directory
3. Server automatically uses `dist/` if available
4. Or use the Vite dev server behind a reverse proxy for better DX



