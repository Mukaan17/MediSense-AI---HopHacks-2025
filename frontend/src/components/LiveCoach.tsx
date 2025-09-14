import React, { useEffect, useRef, useState } from 'react';
import { MessageCircle, AlertTriangle, ChevronDown, ChevronUp, Lightbulb, Target, TrendingUp, Minimize2, MessageSquare } from 'lucide-react';
import { connectCaseWS, disconnectCaseWS, HUD } from '../lib/wsClient';

interface LiveCoachProps {
  caseId: string;
}

const LiveCoach: React.FC<LiveCoachProps> = ({ caseId }) => {
  const [hud, setHud] = useState<HUD | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [hasTranscription, setHasTranscription] = useState(false);
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

  useEffect(() => {
    if (hud?.transcript_chunk) {
      setHasTranscription(true);
      // Auto-expand when transcription starts
      if (!hasTranscription) {
        setIsMinimized(false);
      }
    }
  }, [hud?.transcript_chunk, hasTranscription]);

  // Reset states when caseId changes
  useEffect(() => {
    setHasTranscription(false);
    setIsMinimized(false);
    setIsExpanded(false);
  }, [caseId]);

  // Show minimized state when no case, no HUD, or user has minimized
  if (!hud || isMinimized) {
    return (
      <div className="fixed bottom-4 right-4 z-50">
        <div className="shadow-xl rounded-xl border border-gray-200 bg-white transition-all duration-300 w-16 h-16 flex items-center justify-center">
          <button
            onClick={() => {
              if (hud) {
                setIsMinimized(false);
              }
            }}
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
      <div className={`shadow-xl rounded-xl border border-gray-200 bg-white transition-all duration-300 ${
        isExpanded ? 'w-96' : 'w-72'
      }`}>
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
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="p-1 hover:bg-gray-100 rounded transition-colors"
              title={isExpanded ? "Collapse" : "Expand"}
            >
              {isExpanded ? (
                <ChevronDown className="h-4 w-4 text-gray-600" />
              ) : (
                <ChevronUp className="h-4 w-4 text-gray-600" />
              )}
            </button>
            {hasTranscription && (
              <button
                onClick={() => setIsMinimized(true)}
                className="p-1 hover:bg-gray-100 rounded transition-colors"
                title="Minimize"
              >
                <Minimize2 className="h-4 w-4 text-gray-600" />
              </button>
            )}
          </div>
        </div>
        <div className="p-3 space-y-2">
          <div className="text-sm text-gray-800">
            <div className="font-medium">Current dx: {hud.dx ?? '—'} ({hud.conf?.toFixed(2) ?? '-'})</div>
            {hud.summary && <div className="text-xs text-gray-600 mt-1">{hud.summary}</div>}
          </div>
          {/* Transcribed text is now handled separately in clinical notes */}
          {hud.next_question && (
            <div className="text-sm">
              <div className="flex items-center space-x-2 mb-2">
                <MessageSquare className="h-4 w-4 text-blue-500" />
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
          
          {/* Expanded diagnostic suggestions */}
          {isExpanded && (
            <div className="border-t pt-3 space-y-3">
              {/* Questioning Guidance */}
              {hud.diagnostic_suggestions && (
                <div className="space-y-2">
                  <div className="flex items-center space-x-2 text-sm font-medium text-gray-700">
                    <MessageSquare className="h-4 w-4 text-blue-500" />
                    <span>Questioning Guidance</span>
                  </div>
                  <div className="space-y-2">
                    {hud.diagnostic_suggestions.map((suggestion: any, index: number) => (
                      <div key={index} className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                        <div className="text-xs font-medium text-blue-800 mb-2">
                          {suggestion.type === 'key_symptom' && '🔍 Key Symptom to Explore'}
                          {suggestion.type === 'differential' && '⚖️ Differential Consideration'}
                          {suggestion.type === 'confidence_boost' && '📈 Confidence Booster'}
                          {suggestion.type === 'red_flag' && '🚨 Red Flag Alert'}
                        </div>
                        <div className="text-sm text-blue-700 mb-1">{suggestion.suggestion}</div>
                        {suggestion.reasoning && (
                          <div className="text-xs text-blue-600 italic">Why: {suggestion.reasoning}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Confidence Analysis */}
              {hud.confidence_analysis && (
                <div className="space-y-2">
                  <div className="flex items-center space-x-2 text-sm font-medium text-gray-700">
                    <TrendingUp className="h-4 w-4 text-green-500" />
                    <span>Confidence Analysis</span>
                  </div>
                  <div className="p-2 bg-green-50 border border-green-200 rounded-lg">
                    <div className="text-xs text-green-800">
                      <div className="mb-1">
                        <span className="font-medium">Current Confidence:</span> {hud.conf ? (hud.conf * 100).toFixed(1) : '0.0'}%
                      </div>
                      {hud.confidence_analysis.factors && (
                        <div className="space-y-1">
                          <div className="font-medium">Supporting Factors:</div>
                          {hud.confidence_analysis.factors.map((factor: string, index: number) => (
                            <div key={index} className="text-xs text-green-700">• {factor}</div>
                          ))}
                        </div>
                      )}
                      {hud.confidence_analysis.missing_info && (
                        <div className="mt-2">
                          <div className="font-medium text-orange-700">Missing Information:</div>
                          {hud.confidence_analysis.missing_info.map((info: string, index: number) => (
                            <div key={index} className="text-xs text-orange-600">• {info}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
              
              {/* Clinical Reasoning */}
              {hud.clinical_reasoning && (
                <div className="space-y-2">
                  <div className="flex items-center space-x-2 text-sm font-medium text-gray-700">
                    <Target className="h-4 w-4 text-purple-500" />
                    <span>Clinical Reasoning</span>
                  </div>
                  <div className="p-2 bg-purple-50 border border-purple-200 rounded-lg">
                    <div className="text-xs text-purple-800">
                      {hud.clinical_reasoning.map((reason: string, index: number) => (
                        <div key={index} className="mb-1">• {reason}</div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default LiveCoach;


