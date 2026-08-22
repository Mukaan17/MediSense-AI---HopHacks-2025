import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Database, Clock, AlertCircle, RefreshCw } from 'lucide-react';
import { KnowledgeBaseMode } from '../types';
import { futureAPI } from '../services/api';
import toast from 'react-hot-toast';

interface KnowledgeBaseToggleProps {
  mode: KnowledgeBaseMode;
  onModeChange: (mode: KnowledgeBaseMode) => void;
  className?: string;
}

/**
 * Knowledge-base info panel. Renders only what the backend's store
 * manifest actually reports (sources, document count, embedding model,
 * build date) - it never invents source names.
 */
const KnowledgeBaseToggle: React.FC<KnowledgeBaseToggleProps> = ({
  mode,
  onModeChange,
  className = ''
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  const refreshSources = async () => {
    setIsLoading(true);
    try {
      const response = await futureAPI.getKnowledgeBaseMode();
      if (response.success && response.data) {
        onModeChange(response.data);
        toast.success('Knowledge base refreshed');
      } else {
        toast.error(response.error || 'Refresh failed');
      }
    } catch (error) {
      toast.error('Refresh error');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={`relative ${className}`}>
      <div className="flex items-center space-x-2">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="btn-secondary text-sm flex items-center space-x-2"
          aria-expanded={showDetails}
        >
          <Database className="h-4 w-4" />
          <span>Knowledge Base</span>
          <div className={`w-2 h-2 rounded-full ${mode.sources.length ? 'bg-green-500' : 'bg-gray-400'}`} />
        </button>

        <button
          onClick={refreshSources}
          disabled={isLoading}
          className="p-2 text-gray-500 hover:text-gray-700 disabled:opacity-50"
          title="Refresh knowledge base info"
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

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
                  aria-label="Close knowledge base panel"
                >
                  ×
                </button>
              </div>

              <div className="space-y-3">
                <div>
                  <span className="text-xs font-medium text-gray-600 uppercase tracking-wide">
                    Data Sources
                  </span>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {mode.sources.length > 0 ? (
                      mode.sources.map((source, index) => (
                        <span
                          key={index}
                          className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-full"
                        >
                          {source}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-gray-500">
                        No source manifest recorded
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-600 uppercase tracking-wide">
                    Documents
                  </span>
                  <span className="text-xs text-gray-700 font-medium">
                    {mode.doc_count ?? 'unknown'}
                  </span>
                </div>

                {mode.emb_model && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-gray-600 uppercase tracking-wide">
                      Embedding Model
                    </span>
                    <span className="text-xs text-gray-500 truncate max-w-[10rem]" title={mode.emb_model}>
                      {mode.emb_model.split('/').pop()}
                    </span>
                  </div>
                )}

                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-600 uppercase tracking-wide">
                    Built
                  </span>
                  <div className="flex items-center space-x-1">
                    <Clock className="h-3 w-3 text-gray-400" />
                    <span className="text-xs text-gray-500">
                      {mode.built_at ? new Date(mode.built_at).toLocaleDateString() : 'unknown'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="border-t border-gray-200 pt-4 mt-4">
                <div className="p-2 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <div className="flex items-start space-x-2">
                    <AlertCircle className="h-3 w-3 text-yellow-600 mt-0.5 flex-shrink-0" />
                    <div>
                      <p className="text-xs font-medium text-yellow-800">
                        Advisory Reference Only
                      </p>
                      <p className="text-xs text-yellow-700 mt-1">
                        {mode.description ||
                          'Local demonstration corpus - not a licensed clinical reference.'}
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
