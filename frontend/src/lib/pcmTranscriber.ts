import { API_CONFIG } from '../config/api';
import { getAuthToken } from '../services/api';

// Server-side live transcription: capture mic audio with an AudioWorklet,
// downsample to 16 kHz mono Int16 PCM, and stream raw frames over
// WS /ws/transcribe. The server VAD-segments utterances and replies with
// { transcript, final } JSON messages.
//
// (MediaRecorder cannot feed this path: its timeslice blobs are WebM/Opus
// container fragments, not PCM.)

const TARGET_RATE = 16000;
const FRAME_SAMPLES = 4096; // ~256 ms per network frame

const WORKLET_CODE = `
class PCMCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      this.port.postMessage(channel.slice(0));
    }
    return true;
  }
}
registerProcessor('pcm-capture', PCMCaptureProcessor);
`;

class Downsampler {
  private pos = 0;
  private last = 0;
  constructor(private inRate: number, private outRate: number = TARGET_RATE) {}

  process(input: Float32Array, out: number[]): void {
    const ratio = this.inRate / this.outRate;
    let pos = this.pos;
    for (; pos < input.length; pos += ratio) {
      const i = Math.floor(pos);
      const frac = pos - i;
      const a = i === 0 ? this.last : input[i - 1];
      const b = input[i];
      const sample = a + (b - a) * frac;
      const clamped = Math.max(-1, Math.min(1, sample));
      out.push(Math.round(clamped * 32767));
    }
    this.pos = pos - input.length;
    this.last = input[input.length - 1] ?? this.last;
  }
}

function toWsBase(url: string): string {
  return url.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:').replace(/\/$/, '');
}

export async function startWhisperTranscriber(
  onFinalText: (text: string) => void
): Promise<() => void> {
  const token = getAuthToken();
  const wsUrl = `${toWsBase(API_CONFIG.BASE_URL)}/ws/transcribe` +
    (token ? `?token=${encodeURIComponent(token)}` : '');
  const ws = new WebSocket(wsUrl);
  ws.binaryType = 'arraybuffer';

  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('transcribe WS timeout')), 4000);
    ws.onopen = () => { clearTimeout(timer); resolve(); };
    ws.onerror = () => { clearTimeout(timer); reject(new Error('transcribe WS failed')); };
  });

  let serverReady = true;
  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.error) {
        serverReady = false;
        return;
      }
      if (msg.transcript && msg.final) onFinalText(msg.transcript);
    } catch {
      // ignore malformed frames
    }
  };

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const AudioContextCtor = window.AudioContext || (window as any).webkitAudioContext;
  const audioContext: AudioContext = new AudioContextCtor();
  const source = audioContext.createMediaStreamSource(stream);
  const downsampler = new Downsampler(audioContext.sampleRate);
  const pending: number[] = [];

  const pushSamples = (chunk: Float32Array) => {
    if (ws.readyState !== WebSocket.OPEN || !serverReady) return;
    downsampler.process(chunk, pending);
    while (pending.length >= FRAME_SAMPLES) {
      const frame = new Int16Array(pending.splice(0, FRAME_SAMPLES));
      ws.send(frame.buffer);
    }
  };

  let workletNode: AudioWorkletNode | null = null;
  let scriptNode: ScriptProcessorNode | null = null;

  if (audioContext.audioWorklet) {
    const blobUrl = URL.createObjectURL(new Blob([WORKLET_CODE], { type: 'application/javascript' }));
    try {
      await audioContext.audioWorklet.addModule(blobUrl);
      workletNode = new AudioWorkletNode(audioContext, 'pcm-capture');
      workletNode.port.onmessage = (e) => pushSamples(e.data as Float32Array);
      source.connect(workletNode);
    } finally {
      URL.revokeObjectURL(blobUrl);
    }
  } else {
    // Older browsers: ScriptProcessor fallback.
    scriptNode = audioContext.createScriptProcessor(4096, 1, 1);
    scriptNode.onaudioprocess = (e) => pushSamples(e.inputBuffer.getChannelData(0).slice(0));
    source.connect(scriptNode);
    scriptNode.connect(audioContext.destination);
  }

  let stopped = false;
  return () => {
    if (stopped) return;
    stopped = true;
    try {
      // Ship any buffered samples, then ask the server to flush the
      // in-progress utterance before the socket closes.
      if (ws.readyState === WebSocket.OPEN) {
        if (pending.length) {
          ws.send(new Int16Array(pending.splice(0, pending.length)).buffer);
        }
        ws.send(JSON.stringify({ event: 'flush' }));
        setTimeout(() => { try { ws.close(); } catch { /* no-op */ } }, 3000);
      } else {
        ws.close();
      }
    } catch { /* no-op */ }
    try { workletNode?.disconnect(); } catch { /* no-op */ }
    try { scriptNode?.disconnect(); } catch { /* no-op */ }
    try { source.disconnect(); } catch { /* no-op */ }
    stream.getTracks().forEach((t) => t.stop());
    void audioContext.close().catch(() => undefined);
  };
}
