# Client Static Files

React and TypeScript client for the ImFusion WebAppKit web interface. It uses
[`@imfusion/sdk`](https://www.npmjs.com/package/@imfusion/sdk) for rendering
and [`@imfusion/sdk-react`](https://www.npmjs.com/package/@imfusion/sdk-react)
for reactive SDK state. Python-specific actions, workflows, and data
synchronization are kept in the `PythonBridge` context.

## Setup

```bash
npm install
```

## Development

Start Vite dev server with hot reload:

```bash
npm run dev
```

Then run your Python app:

```bash
python imfusion_webappkit/examples/webapp_demo.py
```

Open `http://localhost:3000`

## Production

Build optimized bundle:

```bash
npm run build
```

The Python server automatically serves from `dist/` if it exists.

## Files

- `index.html` - Vite entry page
- `src/App.tsx` - Application shell and initial viewer layout
- `src/PythonBridge.tsx` - Typed WebSocket and IMF synchronization bridge
- `src/Header.tsx` - Title bar, import/export dialogs, and status indicator
- `src/Sidebar.tsx` - Collapsible sidebar sections and display options
- `src/operations.tsx` - Action, algorithm, and controller widgets
- `src/DropZone.tsx` - File and folder upload plus sample datasets
- `src/controls.tsx` - Shared input selection and parameter widgets
- `src/PanelResizer.tsx` - Drag and keyboard resizing for side panels
- `src/ContextMenu.tsx` - Viewer context menu overlay
- `src/workflow/` - Workflow panel and its step renderers
- `src/types.ts` - Shared client protocol types
- `styles.css` - Styles
- `vite.config.js` - Vite config (port 3000, proxy to :8000)
