import React, { useEffect, useMemo, useState } from 'react';
import { ChatMessage } from '../types';
import { HUD } from '../lib/wsClient';

interface ConversationChatProps {
  caseId: string;
  hud?: HUD | null;
  className?: string;
}

const ConversationChat: React.FC<ConversationChatProps> = ({ caseId, hud, className }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  useEffect(() => {
    const chunk = hud?.transcript_chunk;
    if (!chunk?.text) return;

    setMessages((prev) => {
      const msg: ChatMessage = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        speaker: chunk.speaker === 'doctor' ? 'doctor' : 'patient',
        text: chunk.text,
        timestamp: new Date(),
      };
      const next = [...prev, msg];
      return next.slice(-50);
    });
  }, [hud?.transcript_chunk, hud?.transcript_chunk?.text, hud?.transcript_chunk?.speaker]);

  const emptyText = useMemo(() => {
    if (!caseId || caseId === 'no-case') return 'Start a live case to see streaming transcript.';
    return 'Listening for transcript chunks...';
  }, [caseId]);

  return (
    <div className={`h-full flex flex-col ${className || ''}`}>
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 text-xs text-gray-600">
        Live Transcript
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-sm text-gray-500">{emptyText}</div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`max-w-[85%] ${m.speaker === 'doctor' ? 'ml-auto' : ''}`}>
            <div
              className={`rounded-lg px-3 py-2 text-sm ${
                m.speaker === 'doctor'
                  ? 'bg-blue-100 text-blue-900'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              <div className="text-[11px] uppercase tracking-wide opacity-70 mb-1">{m.speaker}</div>
              <div>{m.text}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ConversationChat;
