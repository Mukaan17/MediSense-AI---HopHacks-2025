import React from 'react';
import { Activity } from 'lucide-react';

interface LiveCoachProps {
  caseId: string;
}

const LiveCoach: React.FC<LiveCoachProps> = ({ caseId }) => {
  const active = caseId && caseId !== 'no-case';

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-4">
      <div className="bg-white border border-gray-200 rounded-xl px-4 py-2 flex items-center justify-between">
        <div className="flex items-center space-x-2 text-sm">
          <Activity className={`h-4 w-4 ${active ? 'text-green-600' : 'text-gray-400'}`} />
          <span className="font-medium text-gray-800">Live Coach</span>
        </div>
        <div className="text-xs text-gray-600">
          {active ? `Case: ${caseId}` : 'No active live case'}
        </div>
      </div>
    </div>
  );
};

export default LiveCoach;
