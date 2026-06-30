/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the backend API. Empty in dev (uses the Vite proxy);
   *  set to the backend origin in production, e.g. https://gobus-ai-assistant-backend.goai247.com */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
