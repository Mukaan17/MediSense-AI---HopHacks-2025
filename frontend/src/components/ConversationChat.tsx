import React, { useState, useEffect, useRef, forwardRef, useImperativeHandle } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Minimize2 } from 'lucide-react';
import { HUD } from '../lib/wsClient';
import { ChatMessage, ConversationChatProps } from '../types';

interface ConversationChatPropsWithHUD extends ConversationChatProps {
  hud?: HUD | null;
}

export interface ConversationChatRef {
  addTranscriptMessage: (text: string, speaker?: 'patient' | 'doctor') => void;
  resetChat: () => void;
}

const ConversationChat = forwardRef<ConversationChatRef, ConversationChatPropsWithHUD>(({ caseId, hud, onMinimize, className = '' }, ref) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isInitialized, setIsInitialized] = useState(false);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  const scrollToBottom = () => {
    if (messagesEndRef.current) {
      // Find the scrollable container (the messages area)
      const messagesContainer = messagesEndRef.current.closest('.overflow-y-auto');
      if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      } else {
        // Fallback to scrollIntoView with more specific options
        messagesEndRef.current.scrollIntoView({ 
          behavior: 'smooth',
          block: 'end',
          inline: 'nearest'
        });
      }
    }
  };

  useEffect(() => {
    // Only scroll if there are messages and component is initialized
    if (messages.length > 0 && isInitialized) {
      // Use setTimeout to ensure DOM is updated
      setTimeout(() => {
        scrollToBottom();
      }, 100);
    }
  }, [messages, isInitialized]);

  // Initialize with iOS call screening style messages
  useEffect(() => {
    if (messages.length === 0) {
      setMessages([
        {
          id: 'system-welcome',
          speaker: 'doctor',
          text: 'Hi, if you record your name and reason for calling, I\'ll see if this person is available.',
          timestamp: new Date()
        }
      ]);
      // Mark as initialized after setting initial message
      setTimeout(() => {
        setIsInitialized(true);
      }, 500);
    }
  }, [messages.length]);

  // Add doctor responses from HUD data
  useEffect(() => {
    if (hud?.next_question && messages.length > 0) {
      // Check if we already have this question to avoid duplicates
      const lastMessage = messages[messages.length - 1];
      if (lastMessage.speaker === 'doctor' && lastMessage.text !== hud.next_question) {
        const newMessage: ChatMessage = {
          id: `hud-${Date.now()}`,
          speaker: 'doctor',
          text: hud.next_question,
          timestamp: new Date()
        };
        setMessages(prev => [...prev, newMessage]);
      }
    }
  }, [hud?.next_question, messages]);

  // Add transcript chunks from HUD - automatically populate chat
  useEffect(() => {
    if (hud?.transcript_chunk && hud.transcript_chunk.text) {
      // Check if this is a new transcript chunk to avoid duplicates
      const lastMessage = messages[messages.length - 1];
      if (!lastMessage || lastMessage.text !== hud.transcript_chunk.text) {
        const newMessage: ChatMessage = {
          id: `transcript-${Date.now()}`,
          speaker: hud.transcript_chunk.speaker === 'doctor' ? 'doctor' : 'patient',
          text: hud.transcript_chunk.text,
          timestamp: new Date(),
          confidence: 0.9
        };
        setMessages(prev => [...prev, newMessage]);
      }
    }
  }, [hud?.transcript_chunk, messages]);

  // Add a function to receive direct transcript updates from VoiceRecorder
  const addTranscriptMessage = (text: string, speaker: 'patient' | 'doctor' = 'patient') => {
    const newMessage: ChatMessage = {
      id: `direct-transcript-${Date.now()}`,
      speaker,
      text,
      timestamp: new Date(),
      confidence: 0.9
    };
    setMessages(prev => [...prev, newMessage]);
  };

  // Reset chat to initial state
  const resetChat = () => {
    setMessages([
      {
        id: 'system-welcome',
        speaker: 'doctor',
        text: 'Hi, if you record your name and reason for calling, I\'ll see if this person is available.',
        timestamp: new Date()
      }
    ]);
    setIsInitialized(true);
  };

  // Expose the functions to parent component
  useImperativeHandle(ref, () => ({
    addTranscriptMessage,
    resetChat
  }));


  return (
    <div className={`flex flex-col h-full bg-gray-900 ${className}`}>
              {/* Simple Header */}
              <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
                <div className="text-center flex-1">
                  <div className="text-white text-lg font-medium mb-1">Patient Consultation</div>
                  <div className="text-gray-400 text-sm">Case ID: {caseId.slice(0, 8)}...</div>
                </div>
                {onMinimize && (
                  <button
                    onClick={onMinimize}
                    className="p-2 hover:bg-gray-700 rounded-full transition-colors"
                    title="Minimize Chat & Coach"
                  >
                    <Minimize2 className="h-4 w-4 text-gray-400" />
                  </button>
                )}
              </div>

      {/* Messages - iOS Call Screening Style */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        <AnimatePresence>
          {messages.map((message) => (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className={`flex ${message.speaker === 'doctor' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`max-w-xs lg:max-w-md ${message.speaker === 'doctor' ? 'ml-12' : 'mr-12'}`}>
                {/* Message Bubble */}
                <div className={`px-4 py-3 rounded-2xl ${
                  message.speaker === 'doctor'
                    ? 'bg-gray-300 text-gray-900'
                    : 'bg-gray-300 text-gray-900'
                }`}>
                  <p className="text-sm leading-relaxed">{message.text}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>


        {/* Live transcribing indicator from HUD */}
        {hud?.transcript_chunk && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className={`flex ${hud.transcript_chunk.speaker === 'doctor' ? 'justify-end' : 'justify-start'}`}
          >
            <div className={`max-w-xs lg:max-w-md ${hud.transcript_chunk.speaker === 'doctor' ? 'ml-12' : 'mr-12'}`}>
              <div className="px-4 py-3 rounded-2xl bg-gray-300 text-gray-900">
                <p className="text-sm leading-relaxed">{hud.transcript_chunk.text}</p>
                <div className="flex items-center space-x-1 mt-2">
                  <div className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-pulse"></div>
                  <div className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }}></div>
                  <div className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }}></div>
                </div>
              </div>
            </div>
          </motion.div>
        )}

        <div ref={messagesEndRef} />
      </div>

    </div>
  );
});

export default ConversationChat;
