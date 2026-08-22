/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Build-time API base URL fallback; runtime config.js takes precedence. */
  readonly VITE_API_URL?: string;
  readonly VITE_ENABLE_VOICE_RECORDING?: string;
  readonly VITE_ENABLE_IMAGE_UPLOAD?: string;
  readonly VITE_ENABLE_EHR_INTEGRATION?: string;
  readonly VITE_DEBUG?: string;
  readonly VITE_LOG_LEVEL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
