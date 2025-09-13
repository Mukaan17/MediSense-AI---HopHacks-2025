// API Configuration
export const API_CONFIG = {
  BASE_URL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
  TIMEOUT: 30000,
  RETRY_ATTEMPTS: 3,
  RETRY_DELAY: 1000,
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
