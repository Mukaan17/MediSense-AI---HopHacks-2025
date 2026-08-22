import React, { useEffect, useState } from 'react';
import { Clock, FileText, ChevronLeft } from 'lucide-react';

import { API_CONFIG } from '../config/api';
import { fetchAuthOptions, normalizeAPIError } from '../services/api';

interface CaseSummary {
  case_id: string;
  patient_id?: string | null;
  created_at: string;
  updated_at: string;
  utterance_count: number;
  top_condition?: string | null;
}

interface TimelineEvent {
  ts: string;
  type: string;
  payload: Record<string, unknown>;
}

const EVENT_LABELS: Record<string, string> = {
  case_created: 'Case created',
  utterance_added: 'Utterance',
  hud_update: 'Analysis update',
  question_feedback: 'Question feedback',
  report_generated: 'Report generated',
};

/**
 * Read-only case history over the durable store: list of past cases and
 * each case's event timeline (what the clinician was shown, when).
 * Deployments without CASE_DB_URL get the backend's explicit 503 message.
 */
const CaseHistory: React.FC<{ onBack: () => void }> = ({ onBack }) => {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [error, setError] = useState<string>('');
  const [selected, setSelected] = useState<CaseSummary | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_CONFIG.BASE_URL}/api/cases`, fetchAuthOptions('GET'));
        const data = await res.json();
        if (!res.ok) throw { response: { data } };
        setCases(data.cases || []);
      } catch (e: any) {
        setError(normalizeAPIError(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const openCase = async (c: CaseSummary) => {
    setSelected(c);
    setTimeline([]);
    try {
      const res = await fetch(
        `${API_CONFIG.BASE_URL}/api/case/${c.case_id}/timeline`, fetchAuthOptions('GET'));
      const data = await res.json();
      if (res.ok) setTimeline(data.events || []);
    } catch {
      // timeline stays empty; the list row already shows the summary
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold text-gray-900">Case History</h2>
        <button onClick={onBack} className="btn-secondary flex items-center space-x-1">
          <ChevronLeft className="h-4 w-4" />
          <span>Back</span>
        </button>
      </div>

      {loading && <div className="text-sm text-gray-500">Loading…</div>}

      {error && (
        <div role="status" className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-900">
          {error}
        </div>
      )}

      {!selected && !error && !loading && (
        <div className="card divide-y divide-gray-100">
          {cases.length === 0 && (
            <div className="text-sm text-gray-500 py-4">No recorded cases yet.</div>
          )}
          {cases.map((c) => (
            <button
              key={c.case_id}
              onClick={() => openCase(c)}
              className="w-full text-left py-3 px-2 hover:bg-gray-50 flex items-center justify-between"
            >
              <div>
                <div className="text-sm font-medium text-gray-900">
                  {c.top_condition || 'No working diagnosis'}
                </div>
                <div className="text-xs text-gray-500">
                  {c.patient_id ? `Patient ${c.patient_id} · ` : ''}
                  {c.utterance_count} utterance{c.utterance_count === 1 ? '' : 's'}
                </div>
              </div>
              <div className="flex items-center space-x-1 text-xs text-gray-400">
                <Clock className="h-3 w-3" />
                <span>{new Date(c.updated_at).toLocaleString()}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {selected && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <FileText className="h-4 w-4 text-gray-500" />
              <span className="text-sm font-medium text-gray-900">
                {selected.top_condition || 'Case'} · {new Date(selected.updated_at).toLocaleString()}
              </span>
            </div>
            <button onClick={() => setSelected(null)} className="text-sm text-gray-500 hover:text-gray-700">
              All cases
            </button>
          </div>
          <ol className="space-y-2">
            {timeline.map((e, i) => (
              <li key={i} className="flex items-start space-x-3 text-sm">
                <span className="text-xs text-gray-400 w-36 flex-shrink-0">
                  {new Date(e.ts).toLocaleTimeString()}
                </span>
                <span className="text-xs font-medium text-gray-600 w-32 flex-shrink-0">
                  {EVENT_LABELS[e.type] || e.type}
                </span>
                <span className="text-gray-800 break-words">
                  {typeof e.payload?.text === 'string' ? e.payload.text
                    : typeof e.payload?.dx === 'string'
                      ? `${e.payload.dx}${typeof e.payload.conf === 'number' ? ` (${((e.payload.conf as number) * 100).toFixed(0)}%)` : ''}`
                      : typeof e.payload?.question === 'string'
                        ? `${e.payload.action}: ${e.payload.question}`
                        : ''}
                </span>
              </li>
            ))}
            {timeline.length === 0 && (
              <li className="text-sm text-gray-500">No events recorded for this case.</li>
            )}
          </ol>
        </div>
      )}
    </div>
  );
};

export default CaseHistory;
