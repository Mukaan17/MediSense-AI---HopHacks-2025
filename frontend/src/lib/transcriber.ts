type OnFinalText = (text: string) => void;

export function startBrowserTranscriber(onFinalText: OnFinalText): () => void {
  const win = window as any;
  const SpeechRecognition = win.SpeechRecognition || win.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    throw new Error('Browser SpeechRecognition API is not available');
  }

  const recognizer = new SpeechRecognition();
  recognizer.continuous = true;
  recognizer.interimResults = false;
  recognizer.lang = 'en-US';

  recognizer.onresult = (event: any) => {
    const items = event?.results || [];
    for (let i = event.resultIndex || 0; i < items.length; i += 1) {
      const item = items[i];
      if (!item?.isFinal) continue;
      const txt = (item[0]?.transcript || '').trim();
      if (txt) onFinalText(txt);
    }
  };

  recognizer.onerror = () => {
    // Keep UX resilient: caller can still use post-recording upload/inference flow.
  };

  recognizer.start();

  return () => {
    try {
      recognizer.stop();
    } catch {
      // no-op
    }
  };
}
