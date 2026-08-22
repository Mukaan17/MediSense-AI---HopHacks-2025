import { useRef, useState } from 'react';
import toast from 'react-hot-toast';

import { API_CONFIG } from '../config/api';
import { getAuthToken } from '../services/api';
import { connectCaseWS, disconnectCaseWS, sendUtterance, HUD } from '../lib/wsClient';

const authHeaders = (): Record<string, string> => {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};

export interface LiveCase {
  activeCaseId: string;
  liveHUD: HUD | null;
  streamingText: string;
  finalReport: string;
  isFinalizing: boolean;
  /** Reads the live-connection flag at call time (a ref, never a stale closure). */
  isLive: () => boolean;
  /** Create the case (image-backed or voice-only), connect the WS, and return
   *  a sender that queues utterances until the socket is ready. */
  startLive: (uploadedImage: File | null) => (txt: string) => void;
  stopLive: () => void;
  finalizeCase: () => Promise<void>;
  resetLiveCase: () => void;
}

/**
 * Owns the live-case lifecycle: case creation, WebSocket connect/disconnect,
 * the pending-utterance queue, HUD + streaming-token state, and the deep
 * final report. Extracted from ClinicalInterface so the container only
 * renders state this hook manages.
 */
export function useLiveCase(): LiveCase {
  const [activeCaseId, setActiveCaseId] = useState<string>('');
  const [liveHUD, setLiveHUD] = useState<HUD | null>(null);
  const [streamingText, setStreamingText] = useState<string>('');
  const [finalReport, setFinalReport] = useState<string>('');
  const [isFinalizing, setIsFinalizing] = useState(false);
  const wsRef = useRef<boolean>(false);
  const pendingUtterancesRef = useRef<string[]>([]);

  const isLive = () => wsRef.current;

  const startLive = (uploadedImage: File | null) => {
    // Return a sender that queues until WS is ready
    const sender = (txt: string) => {
      if (wsRef.current) sendUtterance(txt);
      else pendingUtterancesRef.current.push(txt);
    };

    const ensureCaseAndConnect = async () => {
      let id = activeCaseId;
      try {
        if (!id) {
          let res;
          if (uploadedImage) {
            // Create case with image
            const fd = new FormData();
            fd.append('file', uploadedImage);
            res = await fetch(`${API_CONFIG.BASE_URL}/api/case?live=1`, { method: 'POST', body: fd, headers: authHeaders() });
          } else {
            // Create voice-only case
            res = await fetch(`${API_CONFIG.BASE_URL}/api/case/voice?live=1`, { method: 'POST', headers: authHeaders() });
          }
          if (!res.ok) throw new Error('Failed to create case');
          const data = await res.json();
          id = data?.case_id;
          if (id) setActiveCaseId(id);
        }
        if (!id) return;
        await connectCaseWS(
          id,
          (hud) => {
            // A full HUD update supersedes the token stream;
            // transcript-echo frames carry only transcript_chunk
            // and merge into the existing HUD.
            setStreamingText('');
            setLiveHUD((prev) => ({ ...(prev || {}), ...hud }));
          },
          (token) => setStreamingText((prev) => prev + token)
        );
        wsRef.current = true;
        // Flush any queued utterances
        if (pendingUtterancesRef.current.length) {
          pendingUtterancesRef.current.forEach(t => sendUtterance(t));
          pendingUtterancesRef.current = [];
        }
      } catch (e) {
        console.error(e);
        toast.error('Could not start live session');
      }
    };
    void ensureCaseAndConnect();
    return sender;
  };

  const stopLive = () => {
    disconnectCaseWS();
    wsRef.current = false;
    pendingUtterancesRef.current = [];
  };

  // Deep final report over the whole conversation once a live case ends.
  // Queue-mode deployments return {status: 'queued'} and the report is
  // polled from /api/case/{id}/report; inline mode returns it directly.
  const finalizeCase = async () => {
    if (!activeCaseId) return;
    setIsFinalizing(true);
    try {
      const res = await fetch(`${API_CONFIG.BASE_URL}/api/case/${activeCaseId}/finalize`, { method: 'POST', headers: authHeaders() });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || 'Report generation failed');

      if (data.status === 'queued') {
        const deadline = Date.now() + 180_000;
        while (Date.now() < deadline) {
          await new Promise((r) => setTimeout(r, 2000));
          const poll = await fetch(
            `${API_CONFIG.BASE_URL}/api/case/${activeCaseId}/report`,
            { headers: authHeaders() }
          );
          const status = await poll.json();
          if (!poll.ok) throw new Error(status?.detail || 'Report status unavailable');
          if (status.status === 'complete') {
            setFinalReport(status.report || '');
            toast.success('Final report generated');
            return;
          }
          if (status.status === 'error') {
            throw new Error(status.error || 'Report generation failed');
          }
        }
        throw new Error('Report generation timed out');
      }

      setFinalReport(data.report || '');
      toast.success('Final report generated');
    } catch (e: any) {
      toast.error(e?.message || 'Could not generate final report');
    } finally {
      setIsFinalizing(false);
    }
  };

  const resetLiveCase = () => {
    setActiveCaseId('');
    setLiveHUD(null);
    setStreamingText('');
    setFinalReport('');
    stopLive();
  };

  return {
    activeCaseId,
    liveHUD,
    streamingText,
    finalReport,
    isFinalizing,
    isLive,
    startLive,
    stopLive,
    finalizeCase,
    resetLiveCase,
  };
}
