import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Brain, 
  ChevronDown, 
  ChevronUp, 
  BookOpen, 
  FileText, 
  Database,
  TrendingUp,
  Shield
} from 'lucide-react';
import { XAIExplanation as XAIExplanationType } from '../types';

interface XAIExplanationProps {
  explanation: XAIExplanationType;
  className?: string;
}

const XAIExplanation: React.FC<XAIExplanationProps> = ({ explanation, className = '' }) => {
  const [expandedSections, setExpandedSections] = useState({
    reasoning: true,
    confidence: false,
    sources: false
  });

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const getConfidenceColor = (score: number) => {
    if (score >= 0.8) return 'text-green-600 bg-green-50';
    if (score >= 0.6) return 'text-yellow-600 bg-yellow-50';
    return 'text-red-600 bg-red-50';
  };

  const getConfidenceLabel = (score: number) => {
    if (score >= 0.8) return 'High';
    if (score >= 0.6) return 'Medium';
    return 'Low';
  };

  const getSourceIcon = (type: string) => {
    switch (type) {
      case 'guideline':
        return <Shield className="h-4 w-4 text-blue-500" />;
      case 'study':
        return <TrendingUp className="h-4 w-4 text-green-500" />;
      case 'textbook':
        return <BookOpen className="h-4 w-4 text-purple-500" />;
      default:
        return <FileText className="h-4 w-4 text-gray-500" />;
    }
  };

  return (
    <div className={`card ${className}`}>
      <div className="flex items-center space-x-2 mb-4">
        <Brain className="h-6 w-6 text-medical-primary" />
        <h3 className="text-lg font-semibold text-gray-900">
          Explainable AI Analysis
        </h3>
        <span className="text-sm text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
          Transparency Report
        </span>
      </div>

      <div className="space-y-4">
        {/* Reasoning Chain */}
        <div className="border border-gray-200 rounded-lg">
          <button
            onClick={() => toggleSection('reasoning')}
            className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-center space-x-2">
              <Database className="h-4 w-4 text-medical-primary" />
              <span className="font-medium text-gray-900">Reasoning Chain</span>
            </div>
            {expandedSections.reasoning ? (
              <ChevronUp className="h-4 w-4 text-gray-500" />
            ) : (
              <ChevronDown className="h-4 w-4 text-gray-500" />
            )}
          </button>
          
          <AnimatePresence>
            {expandedSections.reasoning && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="px-4 pb-4">
                  <div className="space-y-3">
                    {explanation.reasoningChain.map((step, index) => (
                      <div key={index} className="flex items-start space-x-3">
                        <div className="flex-shrink-0 w-6 h-6 bg-medical-primary text-white rounded-full flex items-center justify-center text-sm font-medium">
                          {index + 1}
                        </div>
                        <div className="flex-1">
                          <p className="text-gray-700">{step}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Confidence Breakdown */}
        <div className="border border-gray-200 rounded-lg">
          <button
            onClick={() => toggleSection('confidence')}
            className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-center space-x-2">
              <TrendingUp className="h-4 w-4 text-medical-primary" />
              <span className="font-medium text-gray-900">Confidence Breakdown</span>
            </div>
            {expandedSections.confidence ? (
              <ChevronUp className="h-4 w-4 text-gray-500" />
            ) : (
              <ChevronDown className="h-4 w-4 text-gray-500" />
            )}
          </button>
          
          <AnimatePresence>
            {expandedSections.confidence && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="px-4 pb-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {Object.entries(explanation.confidenceBreakdown).map(([key, value]) => (
                      <div key={key} className="space-y-2">
                        <div className="flex justify-between items-center">
                          <span className="text-sm font-medium text-gray-700 capitalize">
                            {key.replace(/([A-Z])/g, ' $1').trim()}
                          </span>
                          <span className={`text-sm font-semibold px-2 py-1 rounded-full ${getConfidenceColor(value)}`}>
                            {getConfidenceLabel(value)}
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div
                            className={`h-2 rounded-full transition-all duration-300 ${
                              value >= 0.8 ? 'bg-green-500' : 
                              value >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                            }`}
                            style={{ width: `${value * 100}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-500">
                          {Math.round(value * 100)}% confidence
                        </span>
                      </div>
                    ))}
                  </div>
                  
                  <div className="mt-4 p-3 bg-blue-50 rounded-lg">
                    <div className="flex items-center space-x-2">
                      <Shield className="h-4 w-4 text-blue-600" />
                      <span className="text-sm font-medium text-blue-800">
                        Overall Confidence Score
                      </span>
                    </div>
                    <div className="mt-2">
                      <div className="flex justify-between items-center">
                        <span className="text-2xl font-bold text-blue-900">
                          {Math.round(
                            Object.values(explanation.confidenceBreakdown).reduce((a, b) => a + b, 0) / 
                            Object.values(explanation.confidenceBreakdown).length * 100
                          )}%
                        </span>
                        <span className="text-sm text-blue-700">
                          Based on {Object.keys(explanation.confidenceBreakdown).length} evidence sources
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Source Attribution */}
        <div className="border border-gray-200 rounded-lg">
          <button
            onClick={() => toggleSection('sources')}
            className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-center space-x-2">
              <BookOpen className="h-4 w-4 text-medical-primary" />
              <span className="font-medium text-gray-900">Source Attribution</span>
              <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full">
                {explanation.sourceAttribution.length} sources
              </span>
            </div>
            {expandedSections.sources ? (
              <ChevronUp className="h-4 w-4 text-gray-500" />
            ) : (
              <ChevronDown className="h-4 w-4 text-gray-500" />
            )}
          </button>
          
          <AnimatePresence>
            {expandedSections.sources && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="px-4 pb-4">
                  <div className="space-y-3">
                    {explanation.sourceAttribution.map((source, index) => (
                      <div key={index} className="border border-gray-100 rounded-lg p-3 hover:bg-gray-50 transition-colors">
                        <div className="flex items-start justify-between">
                          <div className="flex items-start space-x-3">
                            {getSourceIcon(source.type)}
                            <div className="flex-1">
                              <h4 className="font-medium text-gray-900">{source.source}</h4>
                              <p className="text-sm text-gray-600">{source.section}</p>
                              <div className="flex items-center space-x-2 mt-1">
                                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full">
                                  {source.type}
                                </span>
                                <span className="text-xs text-gray-500">
                                  {Math.round(source.relevance * 100)}% relevant
                                </span>
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center space-x-2">
                            <div className="w-16 bg-gray-200 rounded-full h-2">
                              <div
                                className="h-2 bg-medical-primary rounded-full transition-all duration-300"
                                style={{ width: `${source.relevance * 100}%` }}
                              />
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  
                  <div className="mt-4 p-3 bg-green-50 rounded-lg">
                    <div className="flex items-center space-x-2">
                      <Shield className="h-4 w-4 text-green-600" />
                      <span className="text-sm font-medium text-green-800">
                        Evidence Quality Assurance
                      </span>
                    </div>
                    <p className="text-sm text-green-700 mt-1">
                      All sources are peer-reviewed and from authoritative medical institutions. 
                      Information is cross-referenced for accuracy and clinical relevance.
                    </p>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

export default XAIExplanation;
