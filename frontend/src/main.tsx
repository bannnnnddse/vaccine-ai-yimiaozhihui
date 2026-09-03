import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AdminApp } from "./AdminApp";
import "./styles.css";
import "./clinical-workspace.css";
import "./immune-visual-tuning.css";

const RootApp = window.location.pathname.startsWith("/admin") ? AdminApp : App;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RootApp />
  </StrictMode>,
);
