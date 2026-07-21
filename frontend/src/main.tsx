import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { WorkspacePrototype } from "./prototype/WorkspacePrototype";
import "./styles.css";
import "./prototype/workspace-prototype.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <WorkspacePrototype />
  </StrictMode>,
);
