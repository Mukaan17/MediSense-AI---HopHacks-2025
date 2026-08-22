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
  KnowledgeBaseMode,
  APIResponse
} from '../types';
import { API_CONFIG } from '../config/api';

const api = axios.create({
  baseURL: API_CONFIG.BASE_URL,
  timeout: API_CONFIG.TIMEOUT,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const TOKEN_STORAGE_KEY = 'medisense_token';

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

export function getAuthToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_STORAGE_KEY, token);
    else localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // storage unavailable; requests proceed unauthenticated
  }
}

// Request interceptor: logging + bearer token (clinical mode)
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`);
    const token = getAuthToken();
    if (token && config.headers) {
      (config.headers as any)['Authorization'] = `Bearer ${token}`;
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
      // Token missing/expired in clinical mode: let the app show its login.
      window.dispatchEvent(new CustomEvent('medisense:unauthorized'));
    }
    return Promise.reject(error);
  }
);

// Mint a short-lived WS-scoped ticket. WebSocket URLs carry this instead of
// the 8h session JWT so proxy access logs never see a long-lived credential.
export async function getWsTicket(): Promise<string | null> {
  if (!getAuthToken()) return null; // demo mode: sockets are open
  try {
    const response = await api.post('/auth/ws-ticket');
    return response.data?.ticket || null;
  } catch {
    return null;
  }
}

// Exchange credentials for a bearer token (clinical mode)
export async function login(username: string, password: string): Promise<APIResponse<any>> {
  try {
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    const response = await api.post('/auth/login', formData);
    if (response.data?.access_token) {
      setAuthToken(response.data.access_token);
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

// Core API Services
export const clinicalAPI = {
  // Health check
  async healthCheck(): Promise<APIResponse<any>> {
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
  async voiceTranscribe(audioFile: File, description?: string): Promise<APIResponse<any>> {
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
  async listEHRPatients(): Promise<APIResponse<any>> {
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

  async getEHRPatient(patientId: string): Promise<APIResponse<any>> {
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
  async getKnowledgeBaseMode(): Promise<APIResponse<KnowledgeBaseMode>> {
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

  async setKnowledgeBaseMode(mode: string): Promise<APIResponse<KnowledgeBaseMode>> {
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
