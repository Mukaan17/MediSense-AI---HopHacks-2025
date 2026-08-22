import { API_CONFIG } from '../config/api';
import { getAuthToken } from '../services/api';

export interface RankedCondition {
  condition: string;
  confidence?: number;
  reason?: string;
}

export interface HUD {
  dx?: string;
  conf?: number;
  quick_facts?: string;
  next_question?: string;
  alts?: string[];
  alerts?: {
    red_flag?: boolean;
    margin?: number;
  };
  summary?: string;
  ranked?: RankedCondition[];
  transcript_chunk?: {
    speaker: string;
    text: string;
  };
  diagnostic_suggestions?: string[];
  uncertainty_flags?: string[];
  coach?: {
    suggested?: Array<{ q: string; priority?: string; why?: string }>;
  };
  evidence?: {
    posterior_shift?: {
      base_top?: { condition: string; score: number };
      adjusted_top?: { condition: string; score: number };
      delta?: Array<{ condition: string; before: number; after: number; shift: number }>;
      shift_reasons?: string[];
    };
  };
}

let ws: WebSocket | null = null;
let currentCaseId: string | null = null;

function toWsBase(url: string): string {
  return url.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:').replace(/\/$/, '');
}

function normalizeHUD(payload: any): HUD {
  const hud: HUD = payload || {};

  if (!hud.ranked && Array.isArray(payload?.fusion?.top10)) {
    hud.ranked = payload.fusion.top10.slice(0, 5).map((item: any) => ({
      condition: item.condition,
      confidence: item.score,
      reason: item.why,
    }));
  }

  return hud;
}

export async function connectCaseWS(
  caseId: string,
  onUpdate: (hud: HUD) => void,
  onStreamingToken?: (token: string) => void
): Promise<void> {
  disconnectCaseWS();
  currentCaseId = caseId;

  await new Promise<void>((resolve, reject) => {
    const token = getAuthToken();
    const wsUrl = `${toWsBase(API_CONFIG.BASE_URL)}/ws/case/${caseId}` +
      (token ? `?token=${encodeURIComponent(token)}` : '');
    ws = new WebSocket(wsUrl);

    ws.onopen = () => resolve();
    ws.onerror = () => reject(new Error('WebSocket connection failed'));
    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        if (parsed?.type === 'streaming_token') {
          onStreamingToken?.(parsed.token || '');
        } else {
          onUpdate(normalizeHUD(parsed));
        }
      } catch {
        // Ignore malformed payloads to keep live flow stable.
      }
    };
  });
}

export function sendUtterance(text: string, speaker: 'patient' | 'doctor' = 'patient'): void {
  if (!ws || ws.readyState !== WebSocket.OPEN || !currentCaseId) return;
  ws.send(JSON.stringify({ utterance: text, speaker }));
}

export function disconnectCaseWS(): void {
  if (ws) {
    try {
      ws.close();
    } catch {
      // no-op
    }
  }
  ws = null;
  currentCaseId = null;
}
