import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  FileText, 
  Download, 
  Printer, 
  Share2, 
  Calendar,
  User,
  Stethoscope,
  AlertTriangle,
  CheckCircle,
  BookOpen,
  Clock,
  Shield
} from 'lucide-react';
import { ClinicalReport } from '../types';

interface ClinicalReportViewProps {
  report: ClinicalReport;
  className?: string;
}

const ClinicalReportView: React.FC<ClinicalReportViewProps> = ({ report, className = '' }) => {
  const [activeTab, setActiveTab] = useState<'summary' | 'diagnosis' | 'recommendations' | 'education'>('summary');

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return 'text-green-600 bg-green-50';
    if (confidence >= 0.6) return 'text-yellow-600 bg-yellow-50';
    return 'text-red-600 bg-red-50';
  };

  const getConfidenceLabel = (confidence: number) => {
    if (confidence >= 0.8) return 'High Confidence';
    if (confidence >= 0.6) return 'Medium Confidence';
    return 'Low Confidence';
  };

  const tabs = [
    { id: 'summary', label: 'Summary', icon: FileText },
    { id: 'diagnosis', label: 'Diagnosis', icon: Stethoscope },
    { id: 'recommendations', label: 'Recommendations', icon: CheckCircle },
    { id: 'education', label: 'Education', icon: BookOpen }
  ];

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Report Header */}
      <div className="bg-gradient-to-r from-medical-primary to-medical-secondary text-white rounded-lg p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold mb-2">Clinical Analysis Report</h2>
            <div className="flex items-center space-x-4 text-medical-light">
              <div className="flex items-center space-x-1">
                <Calendar className="h-4 w-4" />
                <span className="text-sm">{report.generatedAt ? formatDate(report.generatedAt) : 'Date not available'}</span>
              </div>
              <div className="flex items-center space-x-1">
                <Shield className="h-4 w-4" />
                <span className="text-sm">
                  {Math.round((report.confidence || 0) * 100)}% Confidence
                </span>
              </div>
            </div>
          </div>
          <div className="flex space-x-2">
            <button className="p-2 bg-white/20 hover:bg-white/30 rounded-lg transition-colors">
              <Download className="h-5 w-5" />
            </button>
            <button className="p-2 bg-white/20 hover:bg-white/30 rounded-lg transition-colors">
              <Printer className="h-5 w-5" />
            </button>
            <button className="p-2 bg-white/20 hover:bg-white/30 rounded-lg transition-colors">
              <Share2 className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex space-x-8">
          {tabs.map((tab) => {
            const IconComponent = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === tab.id
                    ? 'border-medical-primary text-medical-primary'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <IconComponent className="h-4 w-4" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab Content */}
      <AnimatePresence mode="wait">
        {activeTab === 'summary' && (
          <motion.div
            key="summary"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-6"
          >
            {/* Patient Summary */}
            <div className="card">
              <div className="flex items-center space-x-2 mb-4">
                <User className="h-5 w-5 text-medical-primary" />
                <h3 className="text-lg font-semibold text-gray-900">Patient Summary</h3>
              </div>
              <p className="text-gray-700 leading-relaxed">{report.patientSummary || 'No patient summary available.'}</p>
            </div>

            {/* Red Flag Alerts */}
            {report.redFlagAlerts && report.redFlagAlerts.length > 0 && (
              <div className="card">
                <div className="flex items-center space-x-2 mb-4">
                  <AlertTriangle className="h-5 w-5 text-red-600" />
                  <h3 className="text-lg font-semibold text-gray-900">Critical Alerts</h3>
                  <span className="text-sm text-red-600 bg-red-100 px-2 py-1 rounded-full">
                    {report.redFlagAlerts.length} Active
                  </span>
                </div>
                <div className="space-y-3">
                  {report.redFlagAlerts.map((alert, index) => (
                    <div key={index} className="p-3 bg-red-50 border border-red-200 rounded-lg">
                      <div className="flex items-center space-x-2 mb-2">
                        <span className="font-semibold text-red-800">{alert.alert}</span>
                        <span className="text-xs bg-red-200 text-red-800 px-2 py-1 rounded-full">
                          {alert.severity?.toUpperCase() || 'UNKNOWN'}
                        </span>
                      </div>
                      <p className="text-sm text-red-700">{alert.action}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Overall Confidence */}
            <div className="card">
              <div className="flex items-center space-x-2 mb-4">
                <Shield className="h-5 w-5 text-medical-primary" />
                <h3 className="text-lg font-semibold text-gray-900">Analysis Confidence</h3>
              </div>
              <div className="flex items-center space-x-4">
                <div className="flex-1">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm font-medium text-gray-700">Overall Confidence</span>
                    <span className={`text-sm font-semibold px-2 py-1 rounded-full ${getConfidenceColor(report.confidence || 0)}`}>
                      {getConfidenceLabel(report.confidence || 0)}
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-3">
                    <div
                      className={`h-3 rounded-full transition-all duration-500 ${
                        (report.confidence || 0) >= 0.8 ? 'bg-green-500' : 
                        (report.confidence || 0) >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                      }`}
                      style={{ width: `${(report.confidence || 0) * 100}%` }}
                    />
                  </div>
                </div>
                <div className="text-2xl font-bold text-medical-primary">
                  {Math.round((report.confidence || 0) * 100)}%
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {activeTab === 'diagnosis' && (
          <motion.div
            key="diagnosis"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-6"
          >
            {report.differentialDiagnosis && report.differentialDiagnosis.length > 0 ? (
              report.differentialDiagnosis.map((diagnosis, index) => (
              <div key={index} className="card">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-gray-900">
                    {index + 1}. {diagnosis.condition.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  </h3>
                  <div className="flex items-center space-x-2">
                    <span className="text-sm text-gray-500">
                      {Math.round(diagnosis.probability * 100)}% probability
                    </span>
                    <span className={`text-xs px-2 py-1 rounded-full ${getConfidenceColor(diagnosis.confidence)}`}>
                      {Math.round(diagnosis.confidence * 100)}% confidence
                    </span>
                  </div>
                </div>
                
                <div className="space-y-4">
                  <p className="text-gray-700">{diagnosis.reasoning}</p>
                  
                  {diagnosis.riskFactors && diagnosis.riskFactors.length > 0 && (
                    <div>
                      <h4 className="font-medium text-gray-900 mb-2">Risk Factors</h4>
                      <ul className="list-disc list-inside space-y-1 text-sm text-gray-700">
                        {diagnosis.riskFactors.map((factor, factorIndex) => (
                          <li key={factorIndex}>{factor}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {diagnosis.supportingEvidence && diagnosis.supportingEvidence.length > 0 && (
                    <div>
                      <h4 className="font-medium text-gray-900 mb-2">Supporting Evidence</h4>
                      <ul className="list-disc list-inside space-y-1 text-sm text-gray-700">
                        {diagnosis.supportingEvidence.map((evidence, evidenceIndex) => (
                          <li key={evidenceIndex}>{evidence}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {diagnosis.redFlags && diagnosis.redFlags.length > 0 && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                      <h4 className="font-medium text-red-800 mb-2">Red Flags</h4>
                      <ul className="list-disc list-inside space-y-1 text-sm text-red-700">
                        {diagnosis.redFlags.map((flag, flagIndex) => (
                          <li key={flagIndex}>{flag}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
              ))
            ) : (
              <div className="card">
                <div className="p-6 text-center">
                  <Stethoscope className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">No Diagnoses Available</h3>
                  <p className="text-gray-600">No differential diagnoses were generated for this case.</p>
                </div>
              </div>
            )}
          </motion.div>
        )}

        {activeTab === 'recommendations' && (
          <motion.div
            key="recommendations"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-6"
          >
            {/* Immediate Recommendations */}
            <div className="card">
              <div className="flex items-center space-x-2 mb-4">
                <CheckCircle className="h-5 w-5 text-green-600" />
                <h3 className="text-lg font-semibold text-gray-900">Immediate Recommendations</h3>
              </div>
              <div className="space-y-3">
                {report.recommendations && report.recommendations.length > 0 ? (
                  report.recommendations.map((recommendation, index) => (
                    <div key={index} className="flex items-start space-x-3 p-3 bg-green-50 border border-green-200 rounded-lg">
                      <div className="w-6 h-6 bg-green-500 text-white rounded-full flex items-center justify-center text-sm font-medium flex-shrink-0">
                        {index + 1}
                      </div>
                      <p className="text-green-800">{recommendation}</p>
                    </div>
                  ))
                ) : (
                  <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
                    <p className="text-gray-600 text-center">No specific recommendations available at this time.</p>
                  </div>
                )}
              </div>
            </div>

            {/* Follow-up */}
            {report.followUp && (
              <div className="card">
                <div className="flex items-center space-x-2 mb-4">
                  <Clock className="h-5 w-5 text-medical-primary" />
                  <h3 className="text-lg font-semibold text-gray-900">Follow-up Plan</h3>
                </div>
                <p className="text-gray-700">{report.followUp}</p>
              </div>
            )}
          </motion.div>
        )}

        {activeTab === 'education' && (
          <motion.div
            key="education"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-6"
          >
            {/* Patient Education */}
            <div className="card">
              <div className="flex items-center space-x-2 mb-4">
                <BookOpen className="h-5 w-5 text-medical-primary" />
                <h3 className="text-lg font-semibold text-gray-900">Patient Education</h3>
              </div>
              <div className="space-y-3">
                {report.patientEducation && report.patientEducation.length > 0 ? (
                  report.patientEducation.map((education, index) => (
                    <div key={index} className="flex items-start space-x-3 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                      <div className="w-6 h-6 bg-blue-500 text-white rounded-full flex items-center justify-center text-sm font-medium flex-shrink-0">
                        {index + 1}
                      </div>
                      <p className="text-blue-800">{education}</p>
                    </div>
                  ))
                ) : (
                  <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
                    <p className="text-gray-600 text-center">No patient education materials available at this time.</p>
                  </div>
                )}
              </div>
            </div>

            {/* Citations */}
            {report.citations && report.citations.length > 0 && (
              <div className="card">
                <div className="flex items-center space-x-2 mb-4">
                  <Shield className="h-5 w-5 text-medical-primary" />
                  <h3 className="text-lg font-semibold text-gray-900">References</h3>
                </div>
                <div className="space-y-2">
                  {report.citations.map((citation, index) => (
                    <div key={index} className="text-sm text-gray-700 p-2 bg-gray-50 rounded-lg">
                      {index + 1}. {citation}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default ClinicalReportView;
