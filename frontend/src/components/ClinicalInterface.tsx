import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload,
  FileText,
  Brain
} from 'lucide-react';
import { useDropzone } from 'react-dropzone';
import toast from 'react-hot-toast';

import { Patient, ClinicalReport, KnowledgeBaseMode, LLMStatus } from '../types';
import { clinicalAPI, futureAPI, apiUtils, getMe } from '../services/api';
import AppHeader from './AppHeader';
import LoginModal from './LoginModal';
import PatientForm from './PatientForm';
import XAIExplanation from './XAIExplanation';
import DifferentialDiagnosis from './DifferentialDiagnosis';
import RedFlagAlerts from './RedFlagAlerts';
import ClinicalReportView from './ClinicalReportView';
import LiveCoach from './LiveCoach';
import VoiceRecorder from './VoiceRecorder';
import ConversationChat, { ConversationChatRef } from './ConversationChat';
import LiveAnalysisPanel from './LiveAnalysisPanel';
import { processAPIResponse } from '../lib/reportMapper';
import { useLiveCase } from '../hooks/useLiveCase';

const ClinicalInterface: React.FC = () => {
  // State management
  const [currentView, setCurrentView] = useState<'input' | 'results' | 'report'>('input');
  const [isLoading, setIsLoading] = useState(false);
  const [patient, setPatient] = useState<Patient>({});
  const [conversation, setConversation] = useState<string[]>([]);
  const [uploadedImage, setUploadedImage] = useState<File | null>(null);
  const [clinicalReport, setClinicalReport] = useState<ClinicalReport | null>(null);
  // Populated from the backend's store manifest - starts empty, never invented.
  const [knowledgeBaseMode, setKnowledgeBaseMode] = useState<KnowledgeBaseMode>({
    mode: 'local',
    sources: [],
  });
  const [llmStatus, setLlmStatus] = useState<LLMStatus | null>(null);
  const [ehrPatients, setEhrPatients] = useState<any[]>([]);
  const [selectedEhrPatient, setSelectedEhrPatient] = useState<string>('');
  const [appMode, setAppMode] = useState<'demo' | 'clinical'>('demo');
  const [showLogin, setShowLogin] = useState(false);

  // Live-case lifecycle (case creation, WS, HUD, final report)
  const {
    activeCaseId, liveHUD, streamingText, finalReport, isFinalizing,
    confidenceHistory, sendQuestionFeedback,
    isLive, startLive, stopLive, finalizeCase, resetLiveCase,
  } = useLiveCase();

  // Refs
  const conversationInputRef = useRef<HTMLTextAreaElement>(null);
  const conversationChatRef = useRef<ConversationChatRef>(null);

  // Health check and load EHR patients on component mount
  useEffect(() => {
    const initializeApp = async () => {
      try {
        // Health check
        const healthResponse = await clinicalAPI.healthCheck();
        if (healthResponse.success) {
          console.log('Backend connected:', healthResponse.data);
          if (healthResponse.data?.app_mode) {
            const mode = healthResponse.data.app_mode === 'clinical' ? 'clinical' : 'demo';
            setAppMode(mode);
            if (mode === 'clinical') {
              // Cookie sessions survive reloads; /auth/me tells us whether
              // this browser already holds one.
              const me = await getMe();
              if (!me.success) {
                setShowLogin(true);
              }
            }
          }
          if (healthResponse.data?.llm) {
            setLlmStatus(healthResponse.data.llm);
          }
        } else {
          console.warn('Backend health check failed:', healthResponse.error);
          toast.error('Backend connection failed. Please ensure the server is running.');
        }

        // Load EHR patients
        const ehrResponse = await futureAPI.listEHRPatients();
        if (ehrResponse.success && ehrResponse.data?.patients) {
          setEhrPatients(ehrResponse.data.patients);
        }

        // Real knowledge-base facts (sources, doc count, build date)
        const kbResponse = await futureAPI.getKnowledgeBaseMode();
        if (kbResponse.success && kbResponse.data) {
          setKnowledgeBaseMode(kbResponse.data);
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

  // Clinical mode requires a bearer token; the API layer fires this event on
  // any 401 so an expired token re-opens the login.
  useEffect(() => {
    const onUnauthorized = () => setShowLogin(true);
    window.addEventListener('medisense:unauthorized', onUnauthorized);
    return () => window.removeEventListener('medisense:unauthorized', onUnauthorized);
  }, []);

  const handleLoginSuccess = async () => {
    setShowLogin(false);
    const ehrResponse = await futureAPI.listEHRPatients();
    if (ehrResponse.success && ehrResponse.data?.patients) {
      setEhrPatients(ehrResponse.data.patients);
    }
  };

  // Voice recording handling. During a live case the WS echoes each utterance
  // back as transcript_chunk (which feeds the chat), so only add to the chat
  // here when no live case is active. isLive() reads a ref at call time - the
  // activeCaseId state here would be a stale closure from record start.
  const handleVoiceTranscription = (transcript: string) => {
    setConversation(prev => [...prev, transcript]);
    if (!isLive()) {
      conversationChatRef.current?.addTranscriptMessage(transcript, 'patient');
    }
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


  return (
    <div className="min-h-screen bg-gray-50">
      <AppHeader
        appMode={appMode}
        knowledgeBaseMode={knowledgeBaseMode}
        onKnowledgeBaseModeChange={setKnowledgeBaseMode}
      />

      <LoginModal open={showLogin} onSuccess={handleLoginSuccess} />

      {/* Degraded-mode visibility: never let missing AI configuration fail
          silently. Both providers absent -> prominent banner; primary absent
          with fallback present -> quieter notice. */}
      {llmStatus && !llmStatus.anthropic && !llmStatus.gemini && (
        <div role="status" className="print:hidden bg-amber-100 border-b border-amber-300 text-amber-900 text-sm px-4 py-2 text-center">
          AI assistance degraded — no language model is configured. Analysis runs on
          retrieval and deterministic rules only.
        </div>
      )}
      {llmStatus && !llmStatus.anthropic && llmStatus.gemini && (
        <div role="status" className="print:hidden bg-gray-100 border-b border-gray-200 text-gray-700 text-xs px-4 py-1 text-center">
          Running on the fallback language model only.
        </div>
      )}

      {/* Live Coach HUD - Always show, minimized when no case */}
      <div className="print:hidden">
        <LiveCoach caseId={activeCaseId || 'no-case'} />
      </div>

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
                      aria-label="Select from EHR patients"
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
                      aria-label="Clinical notes"
                      className="input-field h-32 resize-none"
                      placeholder="Enter patient symptoms, history, or clinical findings..."
                      value={conversation.join('\n')}
                      onChange={(e) => setConversation(e.target.value.split('\n').filter(line => line.trim()))}
                    />
                    
                    {/* Chat Interface */}
                    <div className="mt-4">
                      <div className="shadow-lg rounded-2xl border border-gray-200 bg-white w-full h-[400px] overflow-hidden">
                        <ConversationChat ref={conversationChatRef} caseId={activeCaseId || 'no-case'} hud={liveHUD} className="h-full" />
                      </div>
                    </div>
                    
                    {/* RAG Analysis Section */}
                    <LiveAnalysisPanel
                      hud={liveHUD}
                      streamingText={streamingText}
                      activeCaseId={activeCaseId}
                      finalReport={finalReport}
                      isFinalizing={isFinalizing}
                      onFinalize={finalizeCase}
                      confidenceHistory={confidenceHistory}
                      onQuestionFeedback={sendQuestionFeedback}
                    />

                    <div className="text-xs text-gray-600 mb-2">
                      💡 <strong>Live Transcribing:</strong> Start recording to begin real-time analysis. Works with or without X-ray images.
                    </div>
                    
                    <div className="flex items-center space-x-2">
                      <VoiceRecorder
                        onTranscription={handleVoiceTranscription}
                        onVoiceInference={handleVoiceInference}
                        onStartLive={() => startLive(uploadedImage)}
                        onStopLive={stopLive}
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
                <div className="card h-full flex flex-col">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4 flex-shrink-0">
                    Medical Imaging
                  </h3>
                  <div className="flex-1 flex flex-col min-h-0">
                    {uploadedImage ? (
                      <div className="flex-1 flex flex-col min-h-0">
                        {/* Image Preview */}
                        <div className="flex-1 bg-gray-50 rounded-lg border-2 border-dashed border-gray-200 p-4 mb-4 min-h-0">
                          <img
                            src={URL.createObjectURL(uploadedImage)}
                            alt="Uploaded medical file"
                            className="w-full h-full object-contain rounded-lg"
                          />
                        </div>
                        
                        {/* File Info and Actions */}
                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex-shrink-0">
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center space-x-2">
                              <FileText className="h-4 w-4 text-blue-600" />
                              <span className="text-sm font-medium text-blue-900">Uploaded Image</span>
                            </div>
                            <button
                              onClick={() => setUploadedImage(null)}
                              className="text-sm text-red-600 hover:text-red-800 font-medium"
                            >
                              Remove
                            </button>
                          </div>
                          <p className="text-sm text-blue-700 mb-1">
                            <strong>File:</strong> {uploadedImage.name}
                          </p>
                          <p className="text-xs text-blue-600">
                            <strong>Size:</strong> {(uploadedImage.size / 1024 / 1024).toFixed(2)} MB
                          </p>
                        </div>
                      </div>
                    ) : (
                      <div
                        {...getRootProps()}
                        className={`flex-1 border-2 border-dashed rounded-lg p-2 text-center cursor-pointer transition-colors flex flex-col items-center justify-center min-h-0 ${
                          isDragActive 
                            ? 'border-medical-primary bg-medical-primary/5' 
                            : 'border-gray-300 hover:border-medical-primary hover:bg-gray-50'
                        }`}
                      >
                        <input {...getInputProps({ 'aria-label': 'Upload medical image' })} />
                        <Upload className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                        <div className="space-y-1">
                          <p className="text-sm font-medium text-gray-700">
                            {isDragActive 
                              ? 'Drop the image here...' 
                              : 'Upload Medical Image'
                            }
                          </p>
                          <p className="text-xs text-gray-500">
                            Drag & drop an image, or click to select
                          </p>
                          <p className="text-xs text-gray-400 mt-2">
                            Supports JPEG, PNG, GIF, BMP, TIFF
                          </p>
                        </div>
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
                    onClick={() => {
                      // Reset all state for a new case
                      setCurrentView('input');
                      setPatient({});
                      setConversation([]);
                      setUploadedImage(null);
                      setClinicalReport(null);
                      setSelectedEhrPatient('');
                      resetLiveCase();
                      
                      // Clear conversation input
                      if (conversationInputRef.current) {
                        conversationInputRef.current.value = '';
                      }
                      
                      // Reset chat to initial state
                      conversationChatRef.current?.resetChat();
                      
                      toast.success('New case started');
                    }}
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
              {clinicalReport.redFlagAlerts && clinicalReport.redFlagAlerts.length > 0 && (
                <RedFlagAlerts alerts={clinicalReport.redFlagAlerts} />
              )}

              {/* Differential Diagnosis */}
              <DifferentialDiagnosis diagnoses={clinicalReport.differentialDiagnosis || []} />

              {/* Explainability, built from the backend's evidence payload */}
              {clinicalReport.xai && (
                <XAIExplanation explanation={clinicalReport.xai} />
              )}

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
              <div className="print:hidden flex justify-end space-x-2 mb-4">
                <button onClick={() => setCurrentView('results')} className="btn-secondary">
                  Back to Results
                </button>
                <button onClick={() => window.print()} className="btn-primary">
                  Export PDF
                </button>
              </div>
              {clinicalReport && typeof clinicalReport === 'object' ? (
                <ClinicalReportView report={clinicalReport} />
              ) : (
                <div className="p-6 text-center">
                  <div className="text-gray-500">Report data is not available or corrupted.</div>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
};

export default ClinicalInterface;
