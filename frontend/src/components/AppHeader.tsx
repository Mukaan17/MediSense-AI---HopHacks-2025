import React from 'react';
import { Stethoscope } from 'lucide-react';
import toast from 'react-hot-toast';

import { KnowledgeBaseMode } from '../types';
import KnowledgeBaseToggle from './KnowledgeBaseToggle';
import EHRIntegration from './EHRIntegration';

interface AppHeaderProps {
  appMode: 'demo' | 'clinical';
  knowledgeBaseMode: KnowledgeBaseMode;
  onKnowledgeBaseModeChange: (mode: KnowledgeBaseMode) => void;
}

const AppHeader: React.FC<AppHeaderProps> = ({ appMode, knowledgeBaseMode, onKnowledgeBaseModeChange }) => (
  <header className="print:hidden bg-white shadow-sm border-b border-gray-200">
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div className="flex justify-between items-center h-16">
        <div className="flex items-center space-x-3">
          <Stethoscope className="h-8 w-8 text-medical-primary" />
          <h1 className="text-xl font-semibold text-gray-900">
            Clinical AI Assistant
          </h1>
          {appMode === 'demo' ? (
            <span className="px-2 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wide bg-amber-100 text-amber-800 border border-amber-300">
              Demo mode · synthetic data
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wide bg-blue-100 text-blue-800 border border-blue-300">
              Clinical mode
            </span>
          )}
        </div>

        <div className="flex items-center space-x-4">
          {/* Mocked integrations are demo showcases; clinical mode hides
              them (the backend refuses them with 403 as well). */}
          {appMode === 'demo' && (
            <>
              <KnowledgeBaseToggle
                mode={knowledgeBaseMode}
                onModeChange={onKnowledgeBaseModeChange}
              />
              <EHRIntegration
                integration={{ system: 'epic', importStatus: 'pending' }}
                onImport={(patientId) => {
                  toast.success(`Patient ${patientId} imported`);
                }}
                onExport={() => {
                  toast.success('Report exported to EHR');
                }}
              />
            </>
          )}
        </div>
      </div>
    </div>
  </header>
);

export default AppHeader;
