import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { WebUIProvider } from "@imfusion/web-ui";
import "@imfusion/web-ui/styles.css";
import "./app.css";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <WebUIProvider>
      <App />
    </WebUIProvider>
  </StrictMode>
);
