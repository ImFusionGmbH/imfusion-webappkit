import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import {
  ImFusionCanvas,
  ImFusionError,
  ImFusionLoading,
  ImFusionProvider,
  ImFusionReady,
  useImFusionError,
} from '@imfusion/sdk-react';
import { WebUIProvider } from '@imfusion/web-ui';
import { App } from './App';
import '@imfusion/web-ui/styles.css';
import '../styles.css';

function InitializationError() {
  const error = useImFusionError();
  return (
    <div className="sdk-loading-overlay">
      <div className="sdk-loading-overlay__content">
        <div className="sdk-loading-overlay__text">Failed to initialize: {error.message}</div>
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <WebUIProvider>
      <ImFusionProvider
        options={{ autoInputHandling: true, autoRender: true, autoResize: true }}
      >
        <main id="main-canvas-area">
          <div id="canvas-container">
            <ImFusionCanvas id="canvas" />
          </div>
        </main>
        <ImFusionLoading>
          <div className="sdk-loading-overlay">
            <div className="sdk-loading-overlay__content">
              <div className="sdk-loading-overlay__spinner" />
              <div className="sdk-loading-overlay__text">Loading ImFusion SDK…</div>
            </div>
          </div>
        </ImFusionLoading>
        <ImFusionError>
          <InitializationError />
        </ImFusionError>
        <ImFusionReady><App /></ImFusionReady>
      </ImFusionProvider>
    </WebUIProvider>
  </StrictMode>,
);
