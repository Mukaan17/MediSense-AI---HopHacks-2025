/**
 * @Author: Mukhil Sundararaj
 * @Date:   2025-09-13 13:06:49
 * @Last Modified by:   Mukhil Sundararaj
 * @Last Modified time: 2025-09-13 13:17:35
 */
// Core types for the clinical AI system

export interface Patient {
  id?: string;
  age?: number;
  gender?: 'male' | 'female' | 'other';
  pregnant?: boolean;
  weight?: number;
  height?: number | string; // Support both numeric (cm) and string (ft'in") formats
  bp?: string; // Systolic/Diastolic, e.g., "136/78"
  allergies?: string[];
  medications?: string[];
  pastMedicalHistory?: string[];
}

export interface Symptom {
  id: string;
  name: string;
  severity: 'mild' | 'moderate' | 'severe';
  duration?: string;
  notes?: string;
}

export interface VitalSigns {
  bloodPressure?: {
    systolic: number;
    diastolic: number;
  };
  heartRate?: number;
  temperature?: number;
  respiratoryRate?: number;
  oxygenSaturation?: number;
  weight?: number;
  height?: number;
}

export interface ClinicalFinding {
  type: 'symptom' | 'vital' | 'imaging' | 'lab';
  label: string;
  value?: string | number;
  confidence: number;
  evidence: string[];
  source?: string;
}

export interface DifferentialDiagnosis {
  condition: string;
  probability: number;
  confidence: number;
  riskFactors: string[];
  redFlags: string[];
  supportingEvidence: string[];
  reasoning: string;
}

export interface XAIExplanation {
  reasoningChain: string[];
  confidenceBreakdown: {
    clinicalGuidelines: number;
    imagingEvidence: number;
    symptomMatch: number;
    patientHistory: number;
  };
  sourceAttribution: {
    source: string;
    section: string;
    relevance: number;
    type: 'guideline' | 'study' | 'textbook';
  }[];
}

export interface RedFlagAlert {
  alert: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  trigger: string;
  action: string;
  condition?: string;
}

export interface ClinicalReport {
  patientSummary: string;
  differentialDiagnosis: DifferentialDiagnosis[];
  redFlagAlerts: RedFlagAlert[];
  recommendations: string[];
  followUp: string;
  patientEducation: string[];
  citations: string[];
  generatedAt: string;
  confidence: number;
}

export interface EHRIntegration {
  system: 'epic' | 'cerner' | 'allscripts' | 'other';
  patientId?: string;
  importStatus: 'pending' | 'success' | 'error';
  importedData?: {
    demographics: Partial<Patient>;
    vitals: VitalSigns;
    medications: string[];
    allergies: string[];
    history: string[];
  };
}

export interface KnowledgeBaseMode {
  mode: 'clinical' | 'research';
  sources: string[];
  lastUpdated: string;
}

export interface APIResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  timestamp: string;
}

// API request types
export interface InferRequest {
  utterances: string[];
  patient?: Patient;
  mode?: 'clinical' | 'research';
}

export interface MultimodalInferRequest {
  utterances: string[];
  patient?: Patient;
  image?: File;
  mode?: 'clinical' | 'research';
}

export interface QuickEntryRequest {
  symptoms: string[];
  vitals: VitalSigns;
  patient: Patient;
  voiceNote?: File;
}

// Component props types
export interface XAIComponentProps {
  explanation: XAIExplanation;
  className?: string;
}

export interface DifferentialDiagnosisProps {
  diagnoses: DifferentialDiagnosis[];
  className?: string;
}

export interface RedFlagAlertProps {
  alerts: RedFlagAlert[];
  className?: string;
}

export interface ClinicalReportProps {
  report: ClinicalReport;
  className?: string;
}

export interface EHRIntegrationProps {
  integration: EHRIntegration;
  onImport: (patientId: string) => void;
  onExport: (report: ClinicalReport) => void;
  className?: string;
}
