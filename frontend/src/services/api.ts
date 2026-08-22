/**
 * @Author: Mukhil Sundararaj
 * @Date:   2025-09-13 13:07:10
 * @Last Modified by:   Mukhil Sundararaj
 * @Last Modified time: 2025-09-13 13:17:35
 */
import axios from 'axios';
import {
  InferRequest,
  MultimodalInferRequest,
  ClinicalReport,
  EHRIntegration,
  APIResponse
} from '../types';
import { API_CONFIG } from '../config/api';
import { components } from '../api/schema';

// Response contracts generated from the backend's OpenAPI schema
// (`npm run gen:api`). A breaking backend change fails compilation here
// instead of failing at runtime in a clinic.
export type HealthResponse = components['schemas']['HealthResponse'];
export type LoginResponse = components['schemas']['LoginResponse'];
export type WsTicketResponse = components['schemas']['WsTicketResponse'];
export type EHRPatientsResponse = components['schemas']['EHRPatientsResponse'];
export type EHRPatientDetailResponse = components['schemas']['EHRPatientDetailResponse'];
export type KnowledgeBaseModeResponse = components['schemas']['KnowledgeBaseModeResponse'];
export type CaseCreateResponse = components['schemas']['CaseCreateResponse'];
export type FinalizeCaseResponse = components['schemas']['FinalizeCaseResponse'];
export type TranscriptionResponse = components['schemas']['TranscriptionResponse'];
export type MeResponse = components['schemas']['MeResponse'];

const api = axios.create({
  baseURL: API_CONFIG.BASE_URL,
  timeout: API_CONFIG.TIMEOUT,
  // Session auth rides an httpOnly cookie - XSS cannot read it, unlike the
  // localStorage token this replaced.
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// One-time migration: remove any token persisted by the pre-cookie builds.
try {
  localStorage.removeItem('medisense_token');
} catch {
  // storage unavailable - nothing to migrate
}

// Whether this browser holds a real clinical session (set after login or a
// successful /auth/me). Demo mode leaves it false - demo sockets are open.
let hasSession = false;

export function sessionActive(): boolean {
  return hasSession;
}

// Double-submit CSRF: mutating requests echo the JS-readable CSRF cookie
// in a header; the httpOnly session cookie alone is never enough.
export function getCsrfToken(): string | null {
  try {
    const match = document.cookie.match(/(?:^|;\s*)medisense_csrf=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : null;
  } catch {
    return null;
  }
}

/** RequestInit fragment for raw fetch() calls: cookie credentials plus the
 *  CSRF header on mutating methods. */
export function fetchAuthOptions(method: string = 'GET'): RequestInit {
  const headers: Record<string, string> = {};
  const csrf = getCsrfToken();
  if (csrf && method.toUpperCase() !== 'GET') {
    headers['X-CSRF-Token'] = csrf;
  }
  return { credentials: 'include', headers };
}

// FastAPI errors carry `detail` as a string OR a list of validation-error
// objects (422). Always reduce to a string: these values end up in toasts,
// and rendering an object as a React child crashes the whole tree.
export function normalizeAPIError(error: any): string {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: any) => (typeof d === 'string' ? d : d?.msg || JSON.stringify(d)))
      .join('; ');
  }
  if (detail) return JSON.stringify(detail);
  return error?.message || 'An unexpected error occurred';
}

// Request interceptor: logging + CSRF header for mutating requests
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`);
    const csrf = getCsrfToken();
    if (csrf && config.headers && (config.method || 'get').toLowerCase() !== 'get') {
      (config.headers as any)['X-CSRF-Token'] = csrf;
    }
    // The instance default is application/json; FormData bodies must drop it
    // so the browser sets multipart/form-data with its boundary. Without
    // this, every Form/UploadFile endpoint receives an unparseable body.
    if (typeof FormData !== 'undefined' && config.data instanceof FormData && config.headers) {
      delete (config.headers as any)['Content-Type'];
    }
    return config;
  },
  (error) => {
    console.error('API Request Error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => {
    console.log(`API Response: ${response.status} ${response.config.url}`);
    return response;
  },
  (error) => {
    console.error('API Response Error:', error.response?.data || error.message);
    if (error.response?.status === 401) {
      // Session missing/expired in clinical mode: let the app show its login.
      hasSession = false;
      window.dispatchEvent(new CustomEvent('medisense:unauthorized'));
    }
    return Promise.reject(error);
  }
);

// Mint a short-lived WS-scoped ticket. WebSocket URLs carry this instead of
// the session cookie so proxy access logs never see a long-lived credential.
export async function getWsTicket(): Promise<string | null> {
  if (!hasSession) return null; // demo mode: sockets are open
  try {
    const response = await api.post('/auth/ws-ticket');
    return response.data?.ticket || null;
  } catch {
    return null;
  }
}

// Exchange credentials for an httpOnly cookie session (clinical mode).
export async function login(username: string, password: string): Promise<APIResponse<LoginResponse>> {
  try {
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    const response = await api.post('/auth/login', formData);
    hasSession = true;
    return { success: true, data: response.data, timestamp: new Date().toISOString() };
  } catch (error: any) {
    return {
      success: false,
      error: normalizeAPIError(error),
      timestamp: new Date().toISOString()
    };
  }
}

// Session introspection: 401 in clinical mode without a session. A success
// with authenticated=true marks this browser as holding a real session.
export async function getMe(): Promise<APIResponse<MeResponse>> {
  try {
    const response = await api.get('/auth/me');
    if (response.data?.authenticated) {
      hasSession = true;
    }
    return { success: true, data: response.data, timestamp: new Date().toISOString() };
  } catch (error: any) {
    return {
      success: false,
      error: normalizeAPIError(error),
      timestamp: new Date().toISOString()
    };
  }
}

export async function logout(): Promise<void> {
  try {
    await api.post('/auth/logout');
  } catch {
    // best-effort
  }
  hasSession = false;
}

// Core API Services
export const clinicalAPI = {
  // Health check
  async healthCheck(): Promise<APIResponse<HealthResponse>> {
    try {
      const response = await api.get('/health');
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  },

  // Basic inference. patient_id lets the backend attach the matching EHR
  // record; the server's InferRequest accepts utterances + patient_id.
  async infer(request: InferRequest): Promise<APIResponse<any>> {
    try {
      const response = await api.post('/infer', {
        utterances: request.utterances,
        ...(request.patient?.id ? { patient_id: request.patient.id } : {})
      });
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  },

  // Image inference
  async imageInfer(file: File): Promise<APIResponse<any>> {
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await api.post('/image_infer', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  },

  // Multimodal inference
  async multimodalInfer(request: MultimodalInferRequest): Promise<APIResponse<any>> {
    try {
      const formData = new FormData();
      formData.append('payload', JSON.stringify({
        utterances: request.utterances,
        patient_id: request.patient?.id,
        mode: request.mode || 'clinical'
      }));
      
      if (request.image) {
        formData.append('file', request.image);
      }
      
      const response = await api.post('/multimodal_infer', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  },

  // Voice transcription
  async voiceTranscribe(audioFile: File, description?: string): Promise<APIResponse<TranscriptionResponse>> {
    try {
      const formData = new FormData();
      formData.append('file', audioFile);
      if (description) {
        formData.append('description', description);
      }
      
      const response = await api.post('/voice_transcribe', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  },

  // Voice inference
  async voiceInfer(audioFile: File, patientId?: string, description?: string): Promise<APIResponse<any>> {
    try {
      const formData = new FormData();
      formData.append('file', audioFile);
      if (patientId) {
        formData.append('patient_id', patientId);
      }
      if (description) {
        formData.append('description', description);
      }
      
      const response = await api.post('/voice_infer', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  },

  // Multimodal voice inference
  async multimodalVoiceInfer(audioFile: File, imageFile?: File, patientId?: string, description?: string): Promise<APIResponse<any>> {
    try {
      const formData = new FormData();
      formData.append('audio_file', audioFile);
      if (imageFile) {
        formData.append('image_file', imageFile);
      }
      if (patientId) {
        formData.append('patient_id', patientId);
      }
      if (description) {
        formData.append('description', description);
      }
      
      const response = await api.post('/multimodal_voice_infer', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  },

  // Structured diagnosis
  async structuredDiagnosis(request: MultimodalInferRequest): Promise<APIResponse<any>> {
    try {
      const formData = new FormData();
      formData.append('payload', JSON.stringify({
        utterances: request.utterances,
        patient_id: request.patient?.id
      }));
      
      if (request.image) {
        formData.append('file', request.image);
      }
      
      const response = await api.post('/structured_diagnosis', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  }
};

// Future API endpoints (to be implemented)
export const futureAPI = {
  // EHR Integration
  async importPatientData(patientId: string, ehrSystem: string): Promise<APIResponse<EHRIntegration>> {
    try {
      const formData = new FormData();
      formData.append('patient_id', patientId);
      formData.append('payload', JSON.stringify({
        ehr_system: ehrSystem,
        import_timestamp: new Date().toISOString()
      }));
      
      const response = await api.post('/ehr/import_patient_data', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  },

  async exportClinicalReport(patientId: string, diagnosisResult: any): Promise<APIResponse<ClinicalReport>> {
    try {
      const formData = new FormData();
      formData.append('patient_id', patientId);
      formData.append('diagnosis_result', JSON.stringify(diagnosisResult));
      
      const response = await api.post('/ehr/export_clinical_summary', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  },

  // EHR patient management
  async listEHRPatients(): Promise<APIResponse<EHRPatientsResponse>> {
    try {
      const response = await api.get('/ehr/patients');
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  },

  async getEHRPatient(patientId: string): Promise<APIResponse<EHRPatientDetailResponse>> {
    try {
      const response = await api.get(`/ehr/patients/${patientId}`);
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  },

  // Knowledge Base Management
  async getKnowledgeBaseMode(): Promise<APIResponse<KnowledgeBaseModeResponse>> {
    try {
      const response = await api.get('/knowledge_base/mode');
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  },

  async setKnowledgeBaseMode(mode: string): Promise<APIResponse<KnowledgeBaseModeResponse>> {
    try {
      const formData = new FormData();
      formData.append('mode', mode);
      
      const response = await api.post('/knowledge_base/mode', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  },

  // Voice Processing
  async processVoiceNote(audioFile: File): Promise<APIResponse<{ transcript: string; confidence: number }>> {
    try {
      const formData = new FormData();
      formData.append('file', audioFile);
      
      const response = await api.post('/voice_transcribe', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: normalizeAPIError(error),
        timestamp: new Date().toISOString()
      };
    }
  }
};

// Utility functions
export const apiUtils = {
  // Error handling
  handleAPIError(error: any): string {
    if (error.response?.data?.message && !error.response?.data?.detail) {
      return error.response.data.message;
    }
    return normalizeAPIError(error);
  }
};

export default api;
