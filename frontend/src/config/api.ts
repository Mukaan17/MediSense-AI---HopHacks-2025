// API Configuration.
// Resolution order: runtime config (config.js, templated at container
// start - one build runs against any backend) -> build-time env -> dev
// default. An empty string is meaningful at every level: it makes requests
// relative to the serving origin (the nginx-proxied Docker image) - hence
// explicit undefined checks instead of ||.
declare global {
  interface Window {
    __MEDISENSE_CONFIG__?: { API_URL?: string; SENTRY_DSN?: string };
  }
}

const runtimeConfig =
  (typeof window !== 'undefined' && window.__MEDISENSE_CONFIG__) || {};

export const API_CONFIG = {
  BASE_URL: runtimeConfig.API_URL !== undefined
    ? runtimeConfig.API_URL
    : import.meta.env.VITE_API_URL !== undefined
      ? import.meta.env.VITE_API_URL
      : 'http://localhost:8000',
  TIMEOUT: 30000,
};

// Feature Flags
export const FEATURE_FLAGS = {
  VOICE_RECORDING: import.meta.env.VITE_ENABLE_VOICE_RECORDING !== 'false',
  IMAGE_UPLOAD: import.meta.env.VITE_ENABLE_IMAGE_UPLOAD !== 'false',
  EHR_INTEGRATION: import.meta.env.VITE_ENABLE_EHR_INTEGRATION !== 'false',
};

// Development Settings
export const DEV_CONFIG = {
  DEBUG: import.meta.env.VITE_DEBUG === 'true',
  LOG_LEVEL: import.meta.env.VITE_LOG_LEVEL || 'info',
};
