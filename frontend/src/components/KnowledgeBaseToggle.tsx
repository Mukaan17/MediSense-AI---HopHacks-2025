import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Database, 
  BookOpen, 
  TrendingUp, 
  Clock, 
  CheckCircle,
  AlertCircle,
  RefreshCw
} from 'lucide-react';
import { KnowledgeBaseMode } from '../types';
import { futureAPI } from '../services/api';
import toast from 'react-hot-toast';

interface KnowledgeBaseToggleProps {
  mode: KnowledgeBaseMode;
  onModeChange: (mode: KnowledgeBaseMode) => void;
  className?: string;
}

const KnowledgeBaseToggle: React.FC<KnowledgeBaseToggleProps> = ({ 
  mode, 
  onModeChange, 
  className = '' 
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  const modes = [
    {
      id: 'clinical' as const,
      name: 'Clinical Mode',
      description: 'Standard clinical guidelines and established protocols',
      icon: BookOpen,
      color: 'bg-blue-500',
      sources: ['Clinical Guidelines', 'UpToDate', 'Mayo Clinic', 'Johns Hopkins'],
      lastUpdated: '2024-01-15',
      reliability: 'High'
    },
    {
      id: 'research' as const,
      name: 'Research Mode',
      description: 'Latest research findings and emerging evidence',
      icon: TrendingUp,
      color: 'bg-green-500',
      sources: ['PubMed', 'Cochrane Reviews', 'NEJM', 'Lancet'],
      lastUpdated: '2024-01-20',
      reliability: 'Emerging'
    }
  ];

  const currentMode = modes.find(m => m.id === mode.mode) || modes[0];

  const handleModeChange = async (newMode: 'clinical' | 'research') => {
    if (newMode === mode.mode) return;

    setIsLoading(true);
    try {
      const response = await futureAPI.setKnowledgeBaseMode(newMode);
      
      if (response.success && response.data) {
        onModeChange(response.data);
        toast.success(`Switched to ${newMode} mode`);
      } else {
        toast.error(response.error || 'Mode change failed');
      }
    } catch (error) {
      toast.error('Mode change error');
    } finally {
      setIsLoading(false);
    }
  };

  const refreshSources = async () => {
    setIsLoading(true);
    try {
      const response = await futureAPI.getKnowledgeBaseMode();
      
      if (response.success && response.data) {
        onModeChange(response.data);
        toast.success('Knowledge base refreshed');
      } else {
        toast.error('Refresh failed');
      }
    } catch (error) {
      toast.error('Refresh error');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={`relative ${className}`}>
      {/* Toggle Button */}
      <div className="flex items-center space-x-2">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="btn-secondary text-sm flex items-center space-x-2"
        >
          <Database className="h-4 w-4" />
          <span>{currentMode.name}</span>
          <div className={`w-2 h-2 rounded-full ${currentMode.color}`} />
        </button>
        
        <button
          onClick={refreshSources}
          disabled={isLoading}
          className="p-2 text-gray-500 hover:text-gray-700 disabled:opacity-50"
          title="Refresh knowledge base"
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Details Panel */}
      <AnimatePresence>
        {showDetails && (
          <motion.div
            initial={{ opacity: 0, y: -10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            className="absolute top-full right-0 mt-2 w-80 bg-white rounded-lg shadow-lg border border-gray-200 z-50"
          >
            <div className="p-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-gray-900">Knowledge Base</h3>
                <button
                  onClick={() => setShowDetails(false)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  ×
                </button>
              </div>

              {/* Mode Selection */}
              <div className="space-y-2 mb-4">
                {modes.map((modeOption) => {
                  const IconComponent = modeOption.icon;
                  const isSelected = modeOption.id === mode.mode;
                  
                  return (
                    <button
                      key={modeOption.id}
                      onClick={() => handleModeChange(modeOption.id)}
                      disabled={isLoading}
                      className={`w-full p-3 rounded-lg border text-left transition-colors ${
                        isSelected
                          ? 'border-medical-primary bg-medical-primary/5'
                          : 'border-gray-200 hover:border-gray-300'
                      } ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <div className="flex items-center space-x-3">
                        <div className={`w-3 h-3 rounded-full ${modeOption.color}`} />
                        <IconComponent className="h-4 w-4 text-gray-600" />
                        <div className="flex-1">
                          <div className="flex items-center space-x-2">
                            <span className="font-medium text-sm">{modeOption.name}</span>
                            {isSelected && <CheckCircle className="h-3 w-3 text-green-600" />}
                          </div>
                          <p className="text-xs text-gray-500 mt-1">{modeOption.description}</p>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Current Mode Details */}
              <div className="border-t border-gray-200 pt-4">
                <div className="flex items-center space-x-2 mb-3">
                  <currentMode.icon className="h-4 w-4 text-gray-600" />
                  <span className="font-medium text-sm text-gray-900">
                    {currentMode.name} Details
                  </span>
                </div>

                <div className="space-y-3">
                  {/* Sources */}
                  <div>
                    <span className="text-xs font-medium text-gray-600 uppercase tracking-wide">
                      Data Sources
                    </span>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {currentMode.sources.map((source, index) => (
                        <span
                          key={index}
                          className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-full"
                        >
                          {source}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Last Updated */}
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-gray-600 uppercase tracking-wide">
                      Last Updated
                    </span>
                    <div className="flex items-center space-x-1">
                      <Clock className="h-3 w-3 text-gray-400" />
                      <span className="text-xs text-gray-500">
                        {new Date(currentMode.lastUpdated).toLocaleDateString()}
                      </span>
                    </div>
                  </div>

                  {/* Reliability */}
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-gray-600 uppercase tracking-wide">
                      Reliability
                    </span>
                    <div className="flex items-center space-x-1">
                      {currentMode.reliability === 'High' ? (
                        <CheckCircle className="h-3 w-3 text-green-600" />
                      ) : (
                        <AlertCircle className="h-3 w-3 text-yellow-600" />
                      )}
                      <span className={`text-xs font-medium ${
                        currentMode.reliability === 'High' ? 'text-green-600' : 'text-yellow-600'
                      }`}>
                        {currentMode.reliability}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Mode Comparison */}
              <div className="border-t border-gray-200 pt-4 mt-4">
                <div className="text-xs text-gray-600">
                  <div className="flex items-center space-x-2 mb-2">
                    <Database className="h-3 w-3" />
                    <span className="font-medium">Mode Comparison</span>
                  </div>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span>Clinical Mode:</span>
                      <span className="text-green-600">Established protocols</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Research Mode:</span>
                      <span className="text-blue-600">Latest findings</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Safety Notice */}
              <div className="border-t border-gray-200 pt-4 mt-4">
                <div className="p-2 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <div className="flex items-start space-x-2">
                    <AlertCircle className="h-3 w-3 text-yellow-600 mt-0.5 flex-shrink-0" />
                    <div>
                      <p className="text-xs font-medium text-yellow-800">
                        Clinical Decision Support
                      </p>
                      <p className="text-xs text-yellow-700 mt-1">
                        Research mode includes emerging evidence. Always correlate with clinical judgment.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default KnowledgeBaseToggle;
