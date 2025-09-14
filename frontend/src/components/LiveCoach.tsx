import React, { useEffect, useRef, useState } from 'react';
import { MessageCircle, AlertTriangle } from 'lucide-react';
import { connectCaseWS, disconnectCaseWS, HUD } from '../lib/wsClient';

interface LiveCoachProps {
  caseId: string;
}

const LiveCoach: React.FC<LiveCoachProps> = ({ caseId }) => {
  const [hud, setHud] = useState<HUD | null>(null);
  const [isMinimized, setIsMinimized] = useState(false);
  const wsRef = useRef<boolean>(false);

  useEffect(() => {
    // Don't connect if there's no case
    if (caseId === 'no-case') {
      setHud(null);
      return;
    }

    const connect = async () => {
      try {
        await connectCaseWS(caseId, setHud);
        wsRef.current = true;
      } catch (error) {
        console.error('Failed to connect to WebSocket:', error);
      }
    };
    
    connect();
    return () => {
      disconnectCaseWS();
      wsRef.current = false;
    };
  }, [caseId]);

  // Reset states when caseId changes
  useEffect(() => {
    setIsMinimized(false);
  }, [caseId]);

  // Show minimized state when no case, no HUD, or user has minimized
  if (!hud || isMinimized) {
    return (
      <div className="fixed bottom-4 right-4 z-50">
        <div className="shadow-xl rounded-xl border border-gray-200 bg-white transition-all duration-300 w-16 h-16 flex items-center justify-center">
          <button
            onClick={() => setIsMinimized(false)}
            className="p-2 hover:bg-gray-100 rounded-full transition-colors"
            title={hud ? "Expand Clinician Coach" : "Clinician Coach (No active case)"}
            disabled={!hud}
          >
            <MessageCircle className={`h-6 w-6 ${hud ? 'text-medical-primary' : 'text-gray-400'}`} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <div className={`shadow-xl rounded-xl border border-gray-200 bg-white transition-all duration-300 w-96`}>
        <div className="p-3 border-b flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <MessageCircle className="h-4 w-4 text-medical-primary" />
            <span className="text-sm font-semibold text-gray-900">Clinician Coach</span>
          </div>
          <div className="flex items-center space-x-2">
            {hud.alerts?.red_flag && (
              <div className="flex items-center text-red-600 text-xs space-x-1">
                <AlertTriangle className="h-4 w-4" />
                <span>Red-flag</span>
              </div>
            )}
          </div>
        </div>
        <div className="p-3 space-y-2">
          <div className="text-sm text-gray-800">
            <div className="font-medium">Current dx: {hud.dx ?? '—'} ({hud.conf?.toFixed(2) ?? '-'})</div>
            {hud.summary && <div className="text-xs text-gray-600 mt-1">{hud.summary}</div>}
          </div>
          {hud.next_question && (
            <div className="text-sm">
              <div className="flex items-center space-x-2 mb-2">
                <div className="text-gray-500 text-xs uppercase font-medium">Suggested Question</div>
              </div>
              <div className="mt-1 p-3 rounded-lg bg-blue-50 border border-blue-200 text-gray-900">
                <div className="text-sm font-medium text-blue-800 mb-1">Ask the patient:</div>
                <div className="text-gray-800">{hud.next_question}</div>
              </div>
            </div>
          )}
          {hud.alts && hud.alts.length > 0 && (
            <div className="text-xs text-gray-600">Alts: {hud.alts.join(' • ')}</div>
          )}
          {/* Done indicator when confidence high */}
          {typeof hud.conf === 'number' && hud.conf >= 0.95 && (
            <div className="text-xs font-semibold text-green-600">Done</div>
          )}
          
        </div>
      </div>
    </div>
  );
};

export default LiveCoach;


