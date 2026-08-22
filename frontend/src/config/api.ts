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
    : process.env.REACT_APP_API_URL !== undefined
      ? process.env.REACT_APP_API_URL
      : 'http://localhost:8000',
  TIMEOUT: 30000,
};

// Feature Flags
export const FEATURE_FLAGS = {
  VOICE_RECORDING: process.env.REACT_APP_ENABLE_VOICE_RECORDING !== 'false',
  IMAGE_UPLOAD: process.env.REACT_APP_ENABLE_IMAGE_UPLOAD !== 'false',
  EHR_INTEGRATION: process.env.REACT_APP_ENABLE_EHR_INTEGRATION !== 'false',
};

// Development Settings
export const DEV_CONFIG = {
  DEBUG: process.env.REACT_APP_DEBUG === 'true',
  LOG_LEVEL: process.env.REACT_APP_LOG_LEVEL || 'info',
};
