import React, { useState } from 'react';
import { Brain, Check, X } from 'lucide-react';

import { HUD } from '../lib/wsClient';

interface LiveAnalysisPanelProps {
  hud: HUD | null;
  streamingText: string;
  activeCaseId: string;
  finalReport: string;
  isFinalizing: boolean;
  onFinalize: () => void;
  confidenceHistory?: number[];
  onQuestionFeedback?: (question: string, action: 'accepted' | 'dismissed') => void;
}

/** Single-series confidence trajectory. One hue, 2px line, no grid - the
 *  current value is direct-labeled in text next to it (never in the mark
 *  color); title carries the accessible name. */
const ConfidenceSparkline: React.FC<{ points: number[] }> = ({ points }) => {
  if (points.length < 2) return null;
  const w = 120;
  const h = 28;
  const pad = 2;
  const coords = points
    .map((p, i) => {
      const x = pad + (i * (w - 2 * pad)) / (points.length - 1);
      const y = h - pad - Math.max(0, Math.min(1, p)) * (h - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      role="img"
      aria-label={`Confidence trend over ${points.length} updates, currently ${(points[points.length - 1] * 100).toFixed(0)} percent`}
      className="mt-1"
    >
      <title>Confidence trend</title>
      <polyline
        points={coords}
        fill="none"
        stroke="#2563eb"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
};

/** The "Live RAG Analysis" HUD card: current diagnosis, streamed coach
 *  suggestions, next question, alternatives, and the final-report action.
 *  Renders nothing until the first HUD frame arrives. */
const LiveAnalysisPanel: React.FC<LiveAnalysisPanelProps> = ({
  hud,
  streamingText,
  activeCaseId,
  finalReport,
  isFinalizing,
  onFinalize,
  confidenceHistory = [],
  onQuestionFeedback,
}) => {
  const [handledQuestions, setHandledQuestions] = useState<Set<string>>(new Set());
  if (!hud) return null;

  const handleFeedback = (question: string, action: 'accepted' | 'dismissed') => {
    setHandledQuestions((prev) => new Set(prev).add(question));
    onQuestionFeedback?.(question, action);
  };
  const questionHandled = hud.next_question ? handledQuestions.has(hud.next_question) : false;

  return (
    <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center space-x-2">
          <Brain className="h-4 w-4 text-blue-600" />
          <h3 className="text-sm font-semibold text-blue-900">Live RAG Analysis</h3>
        </div>
        {hud.alerts?.red_flag && (
          <div className="flex items-center space-x-1 text-red-600 text-xs">
            <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
            <span>Red Flag Alert</span>
          </div>
        )}
      </div>

      <div className="space-y-3">
        {/* Current Diagnosis */}
        {hud.dx && (
          <div className="p-3 bg-white rounded border" aria-live="polite">
            <div className="text-xs font-medium text-gray-600 mb-1">Current Diagnosis</div>
            <div className="text-sm font-semibold text-gray-900">{hud.dx}</div>
            {hud.conf && (
              <div className="text-xs text-gray-500 mt-1">
                Confidence: {(hud.conf * 100).toFixed(1)}%
              </div>
            )}
            <ConfidenceSparkline points={confidenceHistory} />
          </div>
        )}

        {/* Quick Facts */}
        {hud.quick_facts && (
          <div className="p-3 bg-white rounded border">
            <div className="text-xs font-medium text-gray-600 mb-1">Key Findings</div>
            <div className="text-sm text-gray-800">{hud.quick_facts}</div>
          </div>
        )}

        {/* Live streaming suggestions (token-by-token) */}
        {streamingText && (
          <div className="p-3 bg-indigo-50 border border-indigo-200 rounded" aria-live="polite">
            <div className="text-xs font-medium text-indigo-800 mb-1">Coach (streaming)</div>
            <div className="text-sm text-indigo-900 whitespace-pre-wrap">
              {streamingText}
              <span className="inline-block w-2 h-4 bg-indigo-500 ml-0.5 animate-pulse" aria-hidden="true"></span>
            </div>
          </div>
        )}

        {/* Next Question, with the clinician's verdict captured as labeled
            feedback (accepted = asked it; dismissed = not useful). */}
        {hud.next_question && !questionHandled && (
          <div className="p-3 bg-yellow-50 border border-yellow-200 rounded" aria-live="polite">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-xs font-medium text-yellow-800 mb-1">Suggested Next Question</div>
                <div className="text-sm text-yellow-900">{hud.next_question}</div>
              </div>
              {onQuestionFeedback && (
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button
                    onClick={() => handleFeedback(hud.next_question!, 'accepted')}
                    aria-label="Mark suggested question as asked"
                    title="Asked it"
                    className="p-1 rounded text-green-700 hover:bg-green-100"
                  >
                    <Check className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => handleFeedback(hud.next_question!, 'dismissed')}
                    aria-label="Dismiss suggested question"
                    title="Not useful"
                    className="p-1 rounded text-red-700 hover:bg-red-100"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Alternatives */}
        {hud.alts && hud.alts.length > 0 && (
          <div className="p-3 bg-white rounded border">
            <div className="text-xs font-medium text-gray-600 mb-1">Alternative Diagnoses</div>
            <div className="text-sm text-gray-800">
              {hud.alts.join(' • ')}
            </div>
          </div>
        )}

        {/* Live Summary */}
        {hud.summary && (
          <div className="p-3 bg-gray-50 rounded border">
            <div className="text-xs font-medium text-gray-600 mb-1">Conversation Summary</div>
            <div className="text-sm text-gray-700">{hud.summary}</div>
          </div>
        )}

        {/* Ranked Conditions */}
        {hud.ranked && hud.ranked.length > 0 && (
          <div className="p-3 bg-white rounded border">
            <div className="text-xs font-medium text-gray-600 mb-2">Top Conditions</div>
            <div className="space-y-1">
              {hud.ranked.slice(0, 3).map((condition, idx) => (
                <div key={idx} className="flex justify-between items-center text-sm">
                  <span className="text-gray-800">{condition.condition}</span>
                  <span className="text-gray-500 text-xs">
                    {(((condition.confidence ?? 0) * 100).toFixed(1))}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Deep final report */}
        {activeCaseId && (
          <div className="p-3 bg-white rounded border">
            <button
              onClick={onFinalize}
              disabled={isFinalizing}
              className="px-3 py-1.5 text-sm rounded bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white"
            >
              {isFinalizing ? 'Generating report…' : 'Generate Final Report'}
            </button>
            {finalReport && (
              <div className="mt-3">
                <div className="text-xs font-medium text-gray-600 mb-1">Advisory Case Report</div>
                <div className="text-sm text-gray-800 whitespace-pre-wrap max-h-80 overflow-y-auto">{finalReport}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default LiveAnalysisPanel;
