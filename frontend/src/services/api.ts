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
  QuickEntryRequest, 
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

// Request interceptor for logging
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`);
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
    return Promise.reject(error);
  }
);

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
        error: error.response?.data?.detail || error.message,
        timestamp: new Date().toISOString()
      };
    }
  },

  // Basic inference
  async infer(request: InferRequest): Promise<APIResponse<any>> {
    try {
      const response = await api.post('/infer', {
        utterances: request.utterances
      });
      return {
        success: true,
        data: response.data,
        timestamp: new Date().toISOString()
      };
    } catch (error: any) {
      return {
        success: false,
        error: error.response?.data?.detail || error.message,
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
        error: error.response?.data?.detail || error.message,
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
        error: error.response?.data?.detail || error.message,
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
        error: error.response?.data?.detail || error.message,
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
        error: error.response?.data?.detail || error.message,
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
        error: error.response?.data?.detail || error.message,
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
        error: error.response?.data?.detail || error.message,
        timestamp: new Date().toISOString()
      };
    }
  }
};

// Future API endpoints (to be implemented)
export const futureAPI = {
  // Quick entry with structured input
  async quickEntry(request: QuickEntryRequest): Promise<APIResponse<ClinicalReport>> {
    try {
      const formData = new FormData();
      formData.append('symptoms', JSON.stringify(request.symptoms));
      formData.append('vitals', JSON.stringify(request.vitals));
      formData.append('patient', JSON.stringify(request.patient));
      
      if (request.voiceNote) {
        formData.append('voice_note', request.voiceNote);
      }
      
      const response = await api.post('/quick_entry', formData, {
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
        error: error.response?.data?.detail || error.message,
        timestamp: new Date().toISOString()
      };
    }
  },

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
        error: error.response?.data?.detail || error.message,
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
        error: error.response?.data?.detail || error.message,
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
        error: error.response?.data?.detail || error.message,
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
        error: error.response?.data?.detail || error.message,
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
        error: error.response?.data?.detail || error.message,
        timestamp: new Date().toISOString()
      };
    }
  },

  async setKnowledgeBaseMode(mode: 'clinical' | 'research'): Promise<APIResponse<KnowledgeBaseMode>> {
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
        error: error.response?.data?.detail || error.message,
        timestamp: new Date().toISOString()
      };
    }
  },

  // Voice Processing
  async processVoiceNote(audioFile: File): Promise<APIResponse<{ transcript: string; confidence: number }>> {
    try {
      const formData = new FormData();
      formData.append('audio', audioFile);
      
      const response = await api.post('/voice/transcribe', formData, {
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
        error: error.response?.data?.detail || error.message,
        timestamp: new Date().toISOString()
      };
    }
  }
};

// Utility functions
export const apiUtils = {
  // Error handling
  handleAPIError(error: any): string {
    if (error.response?.data?.detail) {
      return error.response.data.detail;
    }
    if (error.response?.data?.message) {
      return error.response.data.message;
    }
    if (error.message) {
      return error.message;
    }
    return 'An unexpected error occurred';
  }
};

export default api;
