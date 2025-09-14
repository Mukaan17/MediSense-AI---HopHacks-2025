import React, { useEffect, useRef, useState } from 'react';
import { MessageCircle, AlertTriangle } from 'lucide-react';
import { connectCaseWS, HUD } from '../lib/wsClient';

interface LiveCoachProps {
  caseId: string;
}

const LiveCoach: React.FC<LiveCoachProps> = ({ caseId }) => {
  const [hud, setHud] = useState<HUD | null>(null);
  const wsRef = useRef<ReturnType<typeof connectCaseWS> | null>(null);

  useEffect(() => {
    wsRef.current = connectCaseWS(caseId, setHud);
    return () => wsRef.current?.close();
  }, [caseId]);

  const [lines, setLines] = useState<{speaker?: string; text: string}[]>([]);

  useEffect(() => {
    if (hud?.transcript_chunk) {
      setLines(prev => [...prev, hud.transcript_chunk!].slice(-50));
    }
  }, [hud?.transcript_chunk]);

  if (!hud) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <div className="w-72 shadow-xl rounded-xl border border-gray-200 bg-white">
        <div className="p-3 border-b flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <MessageCircle className="h-4 w-4 text-medical-primary" />
            <span className="text-sm font-semibold text-gray-900">Clinician Coach</span>
          </div>
          {hud.alerts?.red_flag && (
            <div className="flex items-center text-red-600 text-xs space-x-1">
              <AlertTriangle className="h-4 w-4" />
              <span>Red-flag</span>
            </div>
          )}
        </div>
        <div className="p-3 space-y-2">
          <div className="text-sm text-gray-800">
            <div className="font-medium">Current dx: {hud.dx ?? '—'} ({hud.conf?.toFixed(2) ?? '-'})</div>
            {hud.summary && <div className="text-xs text-gray-600 mt-1">{hud.summary}</div>}
          </div>
          {/* Live transcript stream */}
          {lines.length > 0 && (
            <div className="text-xs max-h-28 overflow-auto bg-gray-50 border rounded p-2 space-y-1">
              {lines.map((l, i) => (
                <div key={i}>
                  <span className="font-medium text-gray-700">{l.speaker ? `[${l.speaker}] ` : ''}</span>
                  <span className="text-gray-700">{l.text}</span>
                </div>
              ))}
            </div>
          )}
          {hud.next_question && (
            <div className="text-sm">
              <div className="text-gray-500 text-xs uppercase">Next question</div>
              <div className="mt-1 p-2 rounded bg-gray-50 border text-gray-900">{hud.next_question}</div>
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


