import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Upload, 
  FileText, 
  Stethoscope, 
  Brain
} from 'lucide-react';
import { useDropzone } from 'react-dropzone';
import toast from 'react-hot-toast';

import { Patient, ClinicalReport, KnowledgeBaseMode } from '../types';
import { clinicalAPI, futureAPI, apiUtils } from '../services/api';
import PatientForm from './PatientForm';
import XAIExplanation from './XAIExplanation';
import DifferentialDiagnosis from './DifferentialDiagnosis';
import RedFlagAlerts from './RedFlagAlerts';
import ClinicalReportView from './ClinicalReportView';
import EHRIntegration from './EHRIntegration';
import LiveCoach from './LiveCoach';
import KnowledgeBaseToggle from './KnowledgeBaseToggle';
import VoiceRecorder from './VoiceRecorder';
import { API_CONFIG } from '../config/api';
import { connectCaseWS, disconnectCaseWS, sendUtterance, HUD } from '../lib/wsClient';

const ClinicalInterface: React.FC = () => {
  // State management
  const [currentView, setCurrentView] = useState<'input' | 'results' | 'report'>('input');
  const [isLoading, setIsLoading] = useState(false);
  const [patient, setPatient] = useState<Patient>({});
  const [conversation, setConversation] = useState<string[]>([]);
  const [uploadedImage, setUploadedImage] = useState<File | null>(null);
  const [clinicalReport, setClinicalReport] = useState<ClinicalReport | null>(null);
  const [knowledgeBaseMode, setKnowledgeBaseMode] = useState<KnowledgeBaseMode>({
    mode: 'clinical',
    sources: ['Clinical Guidelines', 'UpToDate'],
    lastUpdated: new Date().toISOString()
  });
  const [ehrPatients, setEhrPatients] = useState<any[]>([]);
  const [selectedEhrPatient, setSelectedEhrPatient] = useState<string>('');
  const [activeCaseId, setActiveCaseId] = useState<string>('');
  const [liveHUD, setLiveHUD] = useState<HUD | null>(null);
  const wsRef = useRef<boolean>(false);
  const pendingUtterancesRef = useRef<string[]>([]);

  // Refs
  const conversationInputRef = useRef<HTMLTextAreaElement>(null);

  // Health check and load EHR patients on component mount
  useEffect(() => {
    const initializeApp = async () => {
      try {
        // Health check
        const healthResponse = await clinicalAPI.healthCheck();
        if (healthResponse.success) {
          console.log('Backend connected:', healthResponse.data);
        } else {
          console.warn('Backend health check failed:', healthResponse.error);
          toast.error('Backend connection failed. Please ensure the server is running.');
        }

        // Load EHR patients
        const ehrResponse = await futureAPI.listEHRPatients();
        if (ehrResponse.success && ehrResponse.data?.patients) {
          setEhrPatients(ehrResponse.data.patients);
        }
      } catch (error) {
        console.error('Initialization error:', error);
        toast.error('Cannot connect to backend. Please check if the server is running on port 8000.');
      }
    };

    initializeApp();
  }, []);

  // Image upload handling
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      'image/*': ['.jpeg', '.jpg', '.png', '.gif', '.bmp', '.tiff']
    },
    maxFiles: 1,
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        setUploadedImage(acceptedFiles[0]);
        toast.success('Image uploaded successfully');
      }
    },
    onDropRejected: () => {
      toast.error('Please upload a valid image file');
    }
  });

  // Voice recording handling
  const handleVoiceTranscription = (transcript: string) => {
    setConversation(prev => [...prev, transcript]);
    toast.success('Voice note transcribed');
  };

  // Voice inference handling
  const handleVoiceInference = async (audioFile: File) => {
    setIsLoading(true);
    try {
      let response;
      
      if (uploadedImage) {
        // Multimodal voice inference (voice + image)
        response = await clinicalAPI.multimodalVoiceInfer(audioFile, uploadedImage, patient.id);
      } else {
        // Voice-only inference
        response = await clinicalAPI.voiceInfer(audioFile, patient.id);
      }
      
      if (response.success) {
        // Process the response and create a clinical report
        const report = processAPIResponse(response.data);
        setClinicalReport(report);
        setCurrentView('results');
        toast.success(uploadedImage ? 'Multimodal voice analysis completed successfully' : 'Voice-based analysis completed successfully');
      } else {
        toast.error(response.error || 'Voice analysis failed');
        console.error('API Error:', response.error);
      }
    } catch (error) {
      const errorMessage = apiUtils.handleAPIError(error);
      toast.error(`Network error: ${errorMessage}`);
      console.error('Voice inference error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // Main inference function
  const handleInference = async () => {
    if (conversation.length === 0 && !uploadedImage) {
      toast.error('Please provide symptoms or upload an image');
      return;
    }

    setIsLoading(true);
    try {
      let response;
      
      if (uploadedImage) {
        // Multimodal inference
        response = await clinicalAPI.multimodalInfer({
          utterances: conversation,
          patient,
          image: uploadedImage || undefined,
          mode: knowledgeBaseMode.mode
        });
      } else {
        // Text-only inference
        response = await clinicalAPI.infer({
          utterances: conversation,
          patient,
          mode: knowledgeBaseMode.mode
        });
      }

      if (response.success) {
        // Process the response and create a clinical report
        const report = processAPIResponse(response.data);
        setClinicalReport(report);
        setCurrentView('results');
        toast.success('Analysis completed successfully');
      } else {
        toast.error(response.error || 'Analysis failed');
        console.error('API Error:', response.error);
      }
    } catch (error) {
      const errorMessage = apiUtils.handleAPIError(error);
      toast.error(`Network error: ${errorMessage}`);
      console.error('Inference error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // Structured diagnosis function
  const handleStructuredDiagnosis = async () => {
    if (conversation.length === 0 && !uploadedImage) {
      toast.error('Please provide symptoms or upload an image');
      return;
    }

    setIsLoading(true);
    try {
      const response = await clinicalAPI.structuredDiagnosis({
        utterances: conversation,
        patient,
        image: uploadedImage || undefined,
        mode: knowledgeBaseMode.mode
      });

      if (response.success) {
        // Process the response and create a clinical report
        const report = processAPIResponse(response.data);
        setClinicalReport(report);
        setCurrentView('results');
        toast.success('Structured diagnosis completed successfully');
      } else {
        toast.error(response.error || 'Structured diagnosis failed');
        console.error('API Error:', response.error);
      }
    } catch (error) {
      const errorMessage = apiUtils.handleAPIError(error);
      toast.error(`Network error: ${errorMessage}`);
      console.error('Structured diagnosis error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // Process API response into clinical report format
  const processAPIResponse = (data: any): ClinicalReport => {
    // Process the actual backend response
    const report: ClinicalReport = {
      patientSummary: data.rag_advisory || data.structured_diagnosis?.summary || "Clinical analysis completed",
      differentialDiagnosis: [],
      redFlagAlerts: [],
      recommendations: [],
      followUp: "",
      patientEducation: [],
      citations: [],
      generatedAt: new Date().toISOString(),
      confidence: 0.0
    };

    // Process differential diagnosis from backend
    if (data.fusion?.top10) {
      report.differentialDiagnosis = data.fusion.top10.slice(0, 5).map((item: any) => ({
        condition: item.condition,
        probability: item.score || 0.0,
        confidence: item.score || 0.0,
        riskFactors: item.risk_factors || [],
        redFlags: item.red_flags || [],
        supportingEvidence: [item.why || 'Combined evidence'],
        reasoning: item.why || 'Based on multimodal analysis'
      }));
    }

    // Process structured diagnosis if available
    if (data.structured_diagnosis) {
      const structured = data.structured_diagnosis;
      
      // Update patient summary
      if (structured.summary) {
        report.patientSummary = structured.summary;
      }
      
      // Process differential diagnosis from structured response
      if (structured.differential_diagnosis) {
        report.differentialDiagnosis = structured.differential_diagnosis.map((diag: any) => ({
          condition: diag.condition || diag.diagnosis,
          probability: diag.probability || diag.confidence || 0.0,
          confidence: diag.confidence || diag.probability || 0.0,
          riskFactors: diag.risk_factors || [],
          redFlags: diag.red_flags || [],
          supportingEvidence: diag.supporting_evidence || [diag.reasoning || 'Clinical evidence'],
          reasoning: diag.reasoning || diag.explanation || 'Based on clinical analysis'
        }));
      }
      
      // Process recommendations
      if (structured.recommendations) {
        report.recommendations = structured.recommendations;
      } else {
        // Fallback: extract recommendations from next_steps in diagnoses
        const nextStepsRecommendations: string[] = [];
        if (structured.differential_diagnosis) {
          structured.differential_diagnosis.forEach((diag: any) => {
            if (diag.next_steps && Array.isArray(diag.next_steps)) {
              nextStepsRecommendations.push(...diag.next_steps);
            }
          });
        }
        
        // Also extract from follow_up_plan if available
        if (structured.clinical_workflow?.follow_up_plan) {
          structured.clinical_workflow.follow_up_plan.forEach((plan: any) => {
            if (plan.actions && Array.isArray(plan.actions)) {
              nextStepsRecommendations.push(...plan.actions);
            }
          });
        }
        
        if (nextStepsRecommendations.length > 0) {
          report.recommendations = nextStepsRecommendations;
        }
      }
      
      // Process follow-up
      if (structured.follow_up) {
        report.followUp = structured.follow_up;
      } else if (structured.clinical_workflow?.follow_up_plan) {
        // Fallback: format follow_up_plan as text
        const followUpText = structured.clinical_workflow.follow_up_plan
          .map((plan: any) => `${plan.timeline}: ${plan.reason}`)
          .join('; ');
        if (followUpText) {
          report.followUp = followUpText;
        }
      }
    }

    // Process recommendations from backend (note: first_steps_non_prescriptive is stripped from answer endpoint)
    if (data.answer?.first_steps_non_prescriptive) {
      report.recommendations = data.answer.first_steps_non_prescriptive;
    }
    
    // Fallback: if no recommendations found, generate basic ones from differential diagnosis
    if (report.recommendations.length === 0 && report.differentialDiagnosis.length > 0) {
      const fallbackRecommendations: string[] = [];
      
      // Add basic recommendations based on top diagnoses
      report.differentialDiagnosis.slice(0, 3).forEach((diag, index) => {
        if (diag.confidence > 0.5) {
          fallbackRecommendations.push(`Consider evaluation for ${diag.condition.replace(/_/g, ' ')}`);
        }
      });
      
      // Add general recommendations
      if (fallbackRecommendations.length === 0) {
        fallbackRecommendations.push("Obtain detailed history and physical examination");
        fallbackRecommendations.push("Consider appropriate diagnostic workup based on clinical presentation");
        fallbackRecommendations.push("Monitor patient response to initial interventions");
      }
      
      report.recommendations = fallbackRecommendations;
    }

    // Process follow-up from backend
    if (data.answer?.follow_up) {
      report.followUp = data.answer.follow_up;
    }

    // Process citations from backend
    if (data.answer?.citations) {
      report.citations = data.answer.citations;
    }

    // Process red flags from backend
    if (data.answer?.red_flags_to_screen) {
      report.redFlagAlerts = data.answer.red_flags_to_screen.map((flag: string) => ({
        alert: flag,
        severity: 'medium' as const,
        trigger: flag,
        action: 'Clinical assessment recommended'
      }));
    }

    // Process risk analysis red flags
    if (data.risk_analysis?.red_flag_alerts) {
      report.redFlagAlerts = data.risk_analysis.red_flag_alerts.map((alert: any) => ({
        alert: alert.alert || alert.message,
        severity: alert.severity || 'medium',
        trigger: alert.trigger || alert.condition,
        action: alert.action || 'Clinical assessment recommended',
        condition: alert.condition
      }));
    }

    // Calculate overall confidence
    if (report.differentialDiagnosis.length > 0) {
      report.confidence = report.differentialDiagnosis.reduce((sum, d) => sum + d.confidence, 0) / report.differentialDiagnosis.length;
    } else if (data.fusion?.top_confidence) {
      report.confidence = data.fusion.top_confidence;
    }

    return report;
  };


  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-3">
              <Stethoscope className="h-8 w-8 text-medical-primary" />
              <h1 className="text-xl font-semibold text-gray-900">
                Clinical AI Assistant
              </h1>
            </div>
            
            <div className="flex items-center space-x-4">
              <KnowledgeBaseToggle 
                mode={knowledgeBaseMode}
                onModeChange={setKnowledgeBaseMode}
              />
              <EHRIntegration 
                integration={{ system: 'epic', importStatus: 'pending' }}
                onImport={(patientId) => {
                  toast.success(`Patient ${patientId} imported`);
                }}
                onExport={(report) => {
                  toast.success('Report exported to EHR');
                }}
              />
            </div>
          </div>
        </div>
      </header>

      {/* Live Coach HUD - Always show, minimized when no case */}
      <LiveCoach caseId={activeCaseId || 'no-case'} />

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <AnimatePresence mode="wait">
          {currentView === 'input' && (
            <motion.div
              key="input"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              className="space-y-6"
            >
              {/* Patient Information */}
              <div className="card">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">
                  Patient Information
                </h2>
                
                {/* EHR Patient Selector */}
                {ehrPatients.length > 0 && (
                  <div className="mb-4">
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Select from EHR Patients
                    </label>
                    <select
                      value={selectedEhrPatient}
                      onChange={(e) => {
                        setSelectedEhrPatient(e.target.value);
                        if (!e.target.value) return;
                        const selectedPatient = ehrPatients.find(p => p.patient_id === e.target.value);
                        if (!selectedPatient) return;

                        const demo = selectedPatient.demographics || {};
                        const vs = selectedPatient.vital_signs || {};

                        // Derive weight in lbs
                        let weight: number | undefined = undefined;
                        if (typeof vs.weight_lbs === 'number') {
                          weight = vs.weight_lbs;
                        } else if (typeof vs.weight_kg === 'number') {
                          weight = Math.round(vs.weight_kg * 2.20462 * 10) / 10;
                        }

                        // Derive height in ft'in format (string)
                        const toFeetInches = (cm: number): string => {
                          const totalInches = Math.round(cm / 2.54);
                          const feet = Math.floor(totalInches / 12);
                          const inches = totalInches % 12;
                          return `${feet}'${inches}"`;
                        };
                        let height: number | string | undefined = undefined;
                        if (typeof vs.height_cm === 'number') {
                          height = toFeetInches(vs.height_cm);
                        } else if (typeof vs.height_in === 'number') {
                          const feet = Math.floor(vs.height_in / 12);
                          const inches = Math.round(vs.height_in % 12);
                          height = `${feet}'${inches}"`;
                        } else if (typeof vs.height_ft_in === 'string') {
                          height = vs.height_ft_in; // e.g., 5'8"
                        }

                        // Derive pregnancy flag best-effort
                        let gender = (demo.sex || '').toLowerCase();
                        if (gender === 'm') gender = 'male';
                        if (gender === 'f') gender = 'female';
                        const pmh: string[] = selectedPatient.pmh || [];
                        const pregnant = gender === 'female' && pmh.some((s: string) => s?.toLowerCase().includes('pregnan'));

                        setPatient({
                          id: selectedPatient.patient_id,
                          age: demo.age,
                          gender: (gender as any),
                          pregnant: Boolean(pregnant),
                          weight,
                          height,
                          bp: typeof vs.bp === 'string' ? vs.bp : undefined,
                          heartRate: typeof vs.hr === 'number' ? vs.hr : undefined,
                          respiratoryRate: typeof vs.rr === 'number' ? vs.rr : undefined,
                          temperature: typeof vs.temp_f === 'number' ? vs.temp_f : undefined,
                          oxygenSaturation: typeof vs.spo2_pct === 'number' ? vs.spo2_pct : undefined,
                          allergies: selectedPatient.allergies || [],
                          medications: selectedPatient.meds || [],
                          pastMedicalHistory: pmh,
                          socialHistory: selectedPatient.social ? {
                            tobacco: selectedPatient.social.tobacco,
                            alcohol: selectedPatient.social.alcohol
                          } : undefined,
                          encounterDate: selectedPatient.encounter_date
                        });
                      }}
                      className="input-field"
                    >
                      <option value="">Select a patient from EHR...</option>
                      {ehrPatients.map((ehrPatient) => (
                        <option key={ehrPatient.patient_id} value={ehrPatient.patient_id}>
                          {ehrPatient.patient_id} - {ehrPatient.demographics?.age}y {ehrPatient.demographics?.sex}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                
                <PatientForm 
                  patient={patient}
                  onPatientChange={setPatient}
                />
              </div>

              {/* Input Methods */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Text Input */}
                <div className="card">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">
                    Clinical Notes
                  </h3>
                  <div className="space-y-4">
                    <textarea
                      ref={conversationInputRef}
                      className="input-field h-32 resize-none"
                      placeholder="Enter patient symptoms, history, or clinical findings..."
                      value={conversation.join('\n')}
                      onChange={(e) => setConversation(e.target.value.split('\n').filter(line => line.trim()))}
                    />
                    
                    {/* RAG Analysis Section */}
                    {liveHUD && (
                      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center space-x-2">
                            <Brain className="h-4 w-4 text-blue-600" />
                            <h3 className="text-sm font-semibold text-blue-900">Live RAG Analysis</h3>
                          </div>
                          {liveHUD.alerts?.red_flag && (
                            <div className="flex items-center space-x-1 text-red-600 text-xs">
                              <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
                              <span>Red Flag Alert</span>
                            </div>
                          )}
                        </div>
                        
                        <div className="space-y-3">
                          {/* Current Diagnosis */}
                          {liveHUD.dx && (
                            <div className="p-3 bg-white rounded border">
                              <div className="text-xs font-medium text-gray-600 mb-1">Current Diagnosis</div>
                              <div className="text-sm font-semibold text-gray-900">{liveHUD.dx}</div>
                              {liveHUD.conf && (
                                <div className="text-xs text-gray-500 mt-1">
                                  Confidence: {(liveHUD.conf * 100).toFixed(1)}%
                                </div>
                              )}
                            </div>
                          )}
                          
                          {/* Quick Facts */}
                          {liveHUD.quick_facts && (
                            <div className="p-3 bg-white rounded border">
                              <div className="text-xs font-medium text-gray-600 mb-1">Key Findings</div>
                              <div className="text-sm text-gray-800">{liveHUD.quick_facts}</div>
                            </div>
                          )}
                          
                          {/* Next Question */}
                          {liveHUD.next_question && (
                            <div className="p-3 bg-yellow-50 border border-yellow-200 rounded">
                              <div className="text-xs font-medium text-yellow-800 mb-1">Suggested Next Question</div>
                              <div className="text-sm text-yellow-900">{liveHUD.next_question}</div>
                            </div>
                          )}
                          
                          {/* Alternatives */}
                          {liveHUD.alts && liveHUD.alts.length > 0 && (
                            <div className="p-3 bg-white rounded border">
                              <div className="text-xs font-medium text-gray-600 mb-1">Alternative Diagnoses</div>
                              <div className="text-sm text-gray-800">
                                {liveHUD.alts.join(' • ')}
                              </div>
                            </div>
                          )}
                          
                          {/* Live Summary */}
                          {liveHUD.summary && (
                            <div className="p-3 bg-gray-50 rounded border">
                              <div className="text-xs font-medium text-gray-600 mb-1">Conversation Summary</div>
                              <div className="text-sm text-gray-700">{liveHUD.summary}</div>
                            </div>
                          )}
                          
                          {/* Ranked Conditions */}
                          {liveHUD.ranked && liveHUD.ranked.length > 0 && (
                            <div className="p-3 bg-white rounded border">
                              <div className="text-xs font-medium text-gray-600 mb-2">Top Conditions</div>
                              <div className="space-y-1">
                                {liveHUD.ranked.slice(0, 3).map((condition, idx) => (
                                  <div key={idx} className="flex justify-between items-center text-sm">
                                    <span className="text-gray-800">{condition.condition}</span>
                                    <span className="text-gray-500 text-xs">
                                      {(condition.confidence * 100).toFixed(1)}%
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                    
                    <div className="text-xs text-gray-600 mb-2">
                      💡 <strong>Live Transcribing:</strong> Start recording to begin real-time analysis. Works with or without X-ray images.
                    </div>
                    
                    <div className="flex items-center space-x-2">
                      <VoiceRecorder 
                        onTranscription={handleVoiceTranscription}
                        onVoiceInference={handleVoiceInference}
                        onStartLive={() => {
                          // Return a sender that queues until WS is ready
                          const sender = (txt: string) => {
                            if (wsRef.current) sendUtterance(txt);
                            else pendingUtterancesRef.current.push(txt);
                          };

                          const ensureCaseAndConnect = async () => {
                            let id = activeCaseId;
                            try {
                              if (!id) {
                                let res;
                                if (uploadedImage) {
                                  // Create case with image
                                  const fd = new FormData();
                                  fd.append('file', uploadedImage);
                                  res = await fetch(`${API_CONFIG.BASE_URL}/api/case?live=1`, { method: 'POST', body: fd });
                                } else {
                                  // Create voice-only case
                                  res = await fetch(`${API_CONFIG.BASE_URL}/api/case/voice?live=1`, { method: 'POST' });
                                }
                                if (!res.ok) throw new Error('Failed to create case');
                                const data = await res.json();
                                id = data?.case_id;
                                if (id) setActiveCaseId(id);
                              }
                              if (!id) return;
                              await connectCaseWS(id, setLiveHUD);
                              wsRef.current = true;
                              // Flush any queued utterances
                              if (pendingUtterancesRef.current.length) {
                                pendingUtterancesRef.current.forEach(t => sendUtterance(t));
                                pendingUtterancesRef.current = [];
                              }
                            } catch (e) {
                              console.error(e);
                              toast.error('Could not start live session');
                            }
                          };
                          void ensureCaseAndConnect();
                          return sender;
                        }}
                        onStopLive={() => {
                          disconnectCaseWS();
                          wsRef.current = false;
                          pendingUtterancesRef.current = [];
                        }}
                      />
                      <button
                        onClick={() => {
                          if (conversationInputRef.current) {
                            conversationInputRef.current.value = '';
                            setConversation([]);
                          }
                        }}
                        className="btn-secondary text-sm px-4 py-2"
                      >
                        Clear
                      </button>
                    </div>
                  </div>
                </div>

                {/* Image Upload */}
                <div className="card">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">
                    Medical Imaging
                  </h3>
                  <div
                    {...getRootProps()}
                    className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                      isDragActive 
                        ? 'border-medical-primary bg-medical-primary/5' 
                        : 'border-gray-300 hover:border-medical-primary'
                    }`}
                  >
                    <input {...getInputProps()} />
                    <Upload className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                    {uploadedImage ? (
                      <div>
                        <p className="text-sm text-gray-600 mb-2">
                          {uploadedImage.name}
                        </p>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setUploadedImage(null);
                          }}
                          className="text-sm text-red-600 hover:text-red-800"
                        >
                          Remove
                        </button>
                      </div>
                    ) : (
                      <div>
                        <p className="text-sm text-gray-600">
                          {isDragActive 
                            ? 'Drop the image here...' 
                            : 'Drag & drop an image, or click to select'
                          }
                        </p>
                        <p className="text-xs text-gray-500 mt-1">
                          Supports JPEG, PNG, GIF, BMP, TIFF
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>


              {/* Quick Entry */}
              <div className="card">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                  Quick Entry
                </h3>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-3">
                    Common Symptoms
                  </label>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                    {[
                      "Chest pain",
                      "Shortness of breath", 
                      "Headache",
                      "Fever",
                      "Nausea",
                      "Dizziness",
                      "Fatigue",
                      "Abdominal pain"
                    ].map((symptom) => (
                      <button
                        key={symptom}
                        onClick={() => {
                          setConversation(prev => {
                            // Check if the symptom already exists in the conversation
                            if (prev.includes(symptom)) {
                              return prev; // Don't add duplicate
                            }
                            return [...prev, symptom]; // Add new symptom
                          });
                        }}
                        className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 hover:border-gray-400 focus:outline-none focus:ring-2 focus:ring-medical-primary focus:border-transparent transition-colors"
                      >
                        {symptom}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex justify-center space-x-4">
                <button
                  onClick={handleInference}
                  disabled={isLoading || (conversation.length === 0 && !uploadedImage)}
                  className="btn-primary px-6 py-3 text-lg disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isLoading ? (
                    <div className="flex items-center space-x-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      <span>Analyzing...</span>
                    </div>
                  ) : (
                    <div className="flex items-center space-x-2">
                      <Brain className="h-5 w-5" />
                      <span>Quick Analysis</span>
                    </div>
                  )}
                </button>
                
                <button
                  onClick={handleStructuredDiagnosis}
                  disabled={isLoading || (conversation.length === 0 && !uploadedImage)}
                  className="btn-secondary px-6 py-3 text-lg disabled:opacity-50 disabled:cursor-not-allowed border-medical-primary text-medical-primary hover:bg-medical-primary hover:text-white"
                >
                  {isLoading ? (
                    <div className="flex items-center space-x-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-medical-primary"></div>
                      <span>Processing...</span>
                    </div>
                  ) : (
                    <div className="flex items-center space-x-2">
                      <FileText className="h-5 w-5" />
                      <span>Structured Diagnosis</span>
                    </div>
                  )}
                </button>
              </div>
            </motion.div>
          )}

          {currentView === 'results' && clinicalReport && (
            <motion.div
              key="results"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-6"
            >
              {/* Results Header */}
              <div className="flex justify-between items-center">
                <h2 className="text-2xl font-semibold text-gray-900">
                  Clinical Analysis Results
                </h2>
                <div className="flex space-x-2">
                  <button
                    onClick={() => setCurrentView('input')}
                    className="btn-secondary"
                  >
                    New Case
                  </button>
                  <button
                    onClick={() => setCurrentView('report')}
                    className="btn-primary"
                  >
                    <FileText className="h-4 w-4 mr-2" />
                    View Report
                  </button>
                </div>
              </div>

              {/* Red Flag Alerts */}
              {clinicalReport.redFlagAlerts.length > 0 && (
                <RedFlagAlerts alerts={clinicalReport.redFlagAlerts} />
              )}

              {/* Differential Diagnosis */}
              <DifferentialDiagnosis diagnoses={clinicalReport.differentialDiagnosis} />

              {/* XAI Explanation */}
              <XAIExplanation 
                explanation={{
                  reasoningChain: [
                    "Patient presents with elevated blood pressure readings",
                    "Associated symptoms suggest uncontrolled hypertension",
                    "Risk factors include age and family history"
                  ],
                  confidenceBreakdown: {
                    clinicalGuidelines: 0.85,
                    imagingEvidence: 0.0,
                    symptomMatch: 0.78,
                    patientHistory: 0.65
                  },
                  sourceAttribution: [
                    {
                      source: "American Heart Association Guidelines",
                      section: "Hypertension Management",
                      relevance: 0.9,
                      type: "guideline"
                    }
                  ]
                }}
              />

              {/* Recommendations */}
              <div className="card">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                  Recommendations
                </h3>
                <ul className="space-y-2">
                  {clinicalReport.recommendations.map((rec, index) => (
                    <li key={index} className="flex items-start space-x-2">
                      <span className="text-medical-primary font-semibold">
                        {index + 1}.
                      </span>
                      <span className="text-gray-700">{rec}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </motion.div>
          )}

          {currentView === 'report' && clinicalReport && (
            <motion.div
              key="report"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <ClinicalReportView report={clinicalReport} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
};

export default ClinicalInterface;
