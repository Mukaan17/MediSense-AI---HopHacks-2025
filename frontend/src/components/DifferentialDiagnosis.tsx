import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Stethoscope, 
  ChevronDown, 
  ChevronUp, 
  AlertTriangle, 
  Shield,
  Users,
  FileText
} from 'lucide-react';
import { DifferentialDiagnosis as DifferentialDiagnosisType } from '../types';

interface DifferentialDiagnosisProps {
  diagnoses: DifferentialDiagnosisType[];
  className?: string;
}

const DifferentialDiagnosis: React.FC<DifferentialDiagnosisProps> = ({ diagnoses, className = '' }) => {
  const [expandedDiagnoses, setExpandedDiagnoses] = useState<Set<number>>(new Set([0]));

  const toggleDiagnosis = (index: number) => {
    const newExpanded = new Set(expandedDiagnoses);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedDiagnoses(newExpanded);
  };

  const getProbabilityColor = (probability: number) => {
    if (probability >= 0.7) return 'text-red-600 bg-red-50 border-red-200';
    if (probability >= 0.4) return 'text-yellow-600 bg-yellow-50 border-yellow-200';
    return 'text-green-600 bg-green-50 border-green-200';
  };

  const getProbabilityLabel = (probability: number) => {
    if (probability >= 0.7) return 'High Probability';
    if (probability >= 0.4) return 'Moderate Probability';
    return 'Low Probability';
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return 'text-green-600';
    if (confidence >= 0.6) return 'text-yellow-600';
    return 'text-red-600';
  };

  const formatConditionName = (condition: string) => {
    return condition
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  return (
    <div className={`card ${className}`}>
      <div className="flex items-center space-x-2 mb-6">
        <Stethoscope className="h-6 w-6 text-medical-primary" />
        <h3 className="text-lg font-semibold text-gray-900">
          Differential Diagnosis
        </h3>
        <span className="text-sm text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
          Top {diagnoses.length} Conditions
        </span>
      </div>

      <div className="space-y-4">
        {diagnoses.map((diagnosis, index) => (
          <div
            key={index}
            className={`border rounded-lg transition-all duration-200 ${
              expandedDiagnoses.has(index)
                ? 'border-medical-primary shadow-md'
                : 'border-gray-200 hover:border-gray-300'
            }`}
          >
            {/* Diagnosis Header */}
            <button
              onClick={() => toggleDiagnosis(index)}
              className="w-full px-4 py-4 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
            >
              <div className="flex items-center space-x-4">
                <div className="flex-shrink-0 w-8 h-8 bg-medical-primary text-white rounded-full flex items-center justify-center text-sm font-bold">
                  {index + 1}
                </div>
                <div className="flex-1">
                  <h4 className="font-semibold text-gray-900 text-lg">
                    {formatConditionName(diagnosis.condition)}
                  </h4>
                  <p className="text-sm text-gray-600 mt-1">
                    {diagnosis.reasoning}
                  </p>
                </div>
              </div>
              
              <div className="flex items-center space-x-4">
                <div className="text-right">
                  <div className={`text-sm font-semibold px-3 py-1 rounded-full border ${getProbabilityColor(diagnosis.probability)}`}>
                    {getProbabilityLabel(diagnosis.probability)}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {Math.round(diagnosis.probability * 100)}% probability
                  </div>
                </div>
                <div className="text-right">
                  <div className={`text-sm font-medium ${getConfidenceColor(diagnosis.confidence)}`}>
                    {Math.round(diagnosis.confidence * 100)}% confidence
                  </div>
                  <div className="text-xs text-gray-500">
                    AI confidence
                  </div>
                </div>
                {expandedDiagnoses.has(index) ? (
                  <ChevronUp className="h-5 w-5 text-gray-500" />
                ) : (
                  <ChevronDown className="h-5 w-5 text-gray-500" />
                )}
              </div>
            </button>

            {/* Expanded Content */}
            <AnimatePresence>
              {expandedDiagnoses.has(index) && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="px-4 pb-4 border-t border-gray-100">
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-4">
                      {/* Risk Factors */}
                      <div className="space-y-3">
                        <div className="flex items-center space-x-2">
                          <Users className="h-4 w-4 text-medical-primary" />
                          <h5 className="font-medium text-gray-900">Risk Factors</h5>
                        </div>
                        {diagnosis.riskFactors.length > 0 ? (
                          <ul className="space-y-2">
                            {diagnosis.riskFactors.map((factor, factorIndex) => (
                              <li key={factorIndex} className="flex items-start space-x-2">
                                <div className="w-1.5 h-1.5 bg-medical-primary rounded-full mt-2 flex-shrink-0" />
                                <span className="text-sm text-gray-700">{factor}</span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-sm text-gray-500 italic">No specific risk factors identified</p>
                        )}
                      </div>

                      {/* Supporting Evidence */}
                      <div className="space-y-3">
                        <div className="flex items-center space-x-2">
                          <FileText className="h-4 w-4 text-medical-primary" />
                          <h5 className="font-medium text-gray-900">Supporting Evidence</h5>
                        </div>
                        {diagnosis.supportingEvidence.length > 0 ? (
                          <ul className="space-y-2">
                            {diagnosis.supportingEvidence.map((evidence, evidenceIndex) => (
                              <li key={evidenceIndex} className="flex items-start space-x-2">
                                <div className="w-1.5 h-1.5 bg-green-500 rounded-full mt-2 flex-shrink-0" />
                                <span className="text-sm text-gray-700">{evidence}</span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-sm text-gray-500 italic">No specific evidence identified</p>
                        )}
                      </div>
                    </div>

                    {/* Red Flags */}
                    {diagnosis.redFlags.length > 0 && (
                      <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                        <div className="flex items-center space-x-2 mb-2">
                          <AlertTriangle className="h-4 w-4 text-red-600" />
                          <h5 className="font-medium text-red-800">Red Flags</h5>
                        </div>
                        <ul className="space-y-1">
                          {diagnosis.redFlags.map((flag, flagIndex) => (
                            <li key={flagIndex} className="flex items-start space-x-2">
                              <div className="w-1.5 h-1.5 bg-red-600 rounded-full mt-2 flex-shrink-0" />
                              <span className="text-sm text-red-700">{flag}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Probability Visualization */}
                    <div className="mt-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium text-gray-700">Probability Assessment</span>
                        <span className="text-sm text-gray-500">
                          {Math.round(diagnosis.probability * 100)}%
                        </span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-3">
                        <div
                          className={`h-3 rounded-full transition-all duration-500 ${
                            diagnosis.probability >= 0.7 ? 'bg-red-500' : 
                            diagnosis.probability >= 0.4 ? 'bg-yellow-500' : 'bg-green-500'
                          }`}
                          style={{ width: `${diagnosis.probability * 100}%` }}
                        />
                      </div>
                      <div className="flex justify-between text-xs text-gray-500 mt-1">
                        <span>Low (0%)</span>
                        <span>Medium (50%)</span>
                        <span>High (100%)</span>
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}
      </div>

      {/* Summary */}
      <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <div className="flex items-center space-x-2 mb-2">
          <Shield className="h-4 w-4 text-blue-600" />
          <h5 className="font-medium text-blue-800">Clinical Decision Support</h5>
        </div>
        <p className="text-sm text-blue-700">
          This differential diagnosis is based on clinical guidelines, evidence-based medicine, 
          and multimodal analysis. Always correlate with clinical judgment and consider patient-specific factors.
        </p>
        <div className="mt-2 flex items-center space-x-4 text-xs text-blue-600">
          <span>• Evidence-based</span>
          <span>• Peer-reviewed sources</span>
          <span>• Clinical guidelines</span>
        </div>
      </div>
    </div>
  );
};

export default DifferentialDiagnosis;
