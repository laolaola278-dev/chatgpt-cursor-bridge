/**
 * Isolated Shadow DOM host.
 *
 * All extension UI lives inside a closed-ish shadow root so ChatGPT styles and
 * scripts are never affected, and the page cannot restyle our controls.
 */

import styles from "./styles.css?inline";

export const HOST_ID = "ccb-extension-root";

export interface UIHost {
  host: HTMLElement;
  shadow: ShadowRoot;
  container: HTMLElement;
  destroy(): void;
}

export function mountShadowHost(doc: Document = document): UIHost {
  const existing = doc.getElementById(HOST_ID);
  existing?.remove();

  const host = doc.createElement("div");
  host.id = HOST_ID;
  host.setAttribute("data-ccb", "root");
  // Keep the host itself inert; the panel inside uses position: fixed.
  host.style.setProperty("all", "initial");

  const shadow = host.attachShadow({ mode: "open" });

  const styleEl = doc.createElement("style");
  styleEl.textContent = styles;
  shadow.appendChild(styleEl);

  const container = doc.createElement("div");
  container.className = "ccb-container";
  shadow.appendChild(container);

  (doc.body ?? doc.documentElement).appendChild(host);

  return {
    host,
    shadow,
    container,
    destroy() {
      host.remove();
    },
  };
}
