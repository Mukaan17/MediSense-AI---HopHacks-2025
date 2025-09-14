import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Square, Play, Pause, Trash2, Brain } from 'lucide-react';
import toast from 'react-hot-toast';
import { clinicalAPI } from '../services/api';
import { startBrowserTranscriber } from '../lib/transcriber';

interface VoiceRecorderProps {
  onTranscription: (transcript: string) => void;
  onVoiceInference?: (audioFile: File) => void;
  onStartLive?: () => ((text: string) => void) | void; // returns send function
  onStopLive?: () => void;
  className?: string;
}

const VoiceRecorder: React.FC<VoiceRecorderProps> = ({ onTranscription, onVoiceInference, onStartLive, onStopLive, className = '' }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioURL, setAudioURL] = useState<string | null>(null);
  const [recordingTime, setRecordingTime] = useState(0);
  const [transcript, setTranscript] = useState('');
  const [isTranscribing, setIsTranscribing] = useState(false);
  const stopSTTRef = useRef<(() => void) | null>(null);
  const liveSendRef = useRef<((text: string) => void) | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
      if (audioURL) {
        URL.revokeObjectURL(audioURL);
      }
    };
  }, [audioURL]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      const chunks: BlobPart[] = [];
      mediaRecorder.ondataavailable = async (event) => {
        if (event.data && event.data.size > 0) {
          chunks.push(event.data);
          // Stream small chunks to backend for near-real-time transcription (optional future)
          // For now, create an object URL and show rolling time only.
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'audio/wav' });
        setAudioBlob(blob);
        const url = URL.createObjectURL(blob);
        setAudioURL(url);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
      setRecordingTime(0);

      timerRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);

      // Start browser STT immediately and push final chunks live
      try {
        if (onStartLive) {
          const sender = onStartLive();
          if (typeof sender === 'function') liveSendRef.current = sender;
        }
        stopSTTRef.current = startBrowserTranscriber((txt) => {
          onTranscription(txt);
          liveSendRef.current?.(txt);
        });
      } catch (e) {
        // Fallback: will only do post-stop transcription
        console.warn('Live STT not available:', e);
      }

      toast.success('Recording started');
    } catch (error) {
      toast.error('Microphone access denied');
      console.error('Recording error:', error);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
      // Stop live STT + WS
      if (stopSTTRef.current) { try { stopSTTRef.current(); } catch {} stopSTTRef.current = null; }
      if (onStopLive) onStopLive();
      toast.success('Recording stopped');
    }
  };

  const playRecording = () => {
    if (audioRef.current && audioURL) {
      if (isPlaying) {
        audioRef.current.pause();
        setIsPlaying(false);
      } else {
        audioRef.current.play();
        setIsPlaying(true);
      }
    }
  };

  const deleteRecording = () => {
    setAudioBlob(null);
    if (audioURL) {
      URL.revokeObjectURL(audioURL);
      setAudioURL(null);
    }
    setTranscript('');
    setRecordingTime(0);
    toast.success('Recording deleted');
  };

  const transcribeRecording = async () => {
    if (!audioBlob) return;

    setIsTranscribing(true);
    try {
      // Convert blob to File for API call
      const audioFile = new File([audioBlob], 'recording.wav', { type: 'audio/wav' });
      
      const response = await clinicalAPI.voiceTranscribe(audioFile, 'Clinical voice note');
      
      if (response.success && response.data) {
        // Extract transcript from the response
        let transcriptText = '';
        
        if (response.data.conversation && response.data.conversation.length > 0) {
          // Extract all utterances from the conversation
          const utterances = response.data.conversation.flatMap((entry: any) => 
            entry.utterances ? entry.utterances.map((u: any) => u.text) : []
          );
          transcriptText = utterances.join(' ');
        } else if (response.data.transcript) {
          transcriptText = response.data.transcript;
        } else {
          transcriptText = 'Transcription completed but no text extracted';
        }
        
        setTranscript(transcriptText);
        onTranscription(transcriptText);
        toast.success('Voice note transcribed successfully');
      } else {
        throw new Error(response.error || 'Transcription failed');
      }
    } catch (error: any) {
      console.error('Transcription error:', error);
      toast.error(`Transcription failed: ${error.message || 'Unknown error'}`);
    } finally {
      setIsTranscribing(false);
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className={`space-y-3 ${className}`}>
      {/* Recording Controls */}
      <div className="flex items-center space-x-2">
        {!isRecording && !audioBlob && (
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={startRecording}
            className="flex items-center space-x-2 px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors"
          >
            <Mic className="h-4 w-4" />
            <span>Start Recording</span>
          </motion.button>
        )}

        {isRecording && (
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={stopRecording}
            className="flex items-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
          >
            <Square className="h-4 w-4" />
            <span>Stop Recording</span>
          </motion.button>
        )}

        {audioBlob && !isRecording && (
          <div className="flex items-center space-x-2">
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={playRecording}
              className="flex items-center space-x-2 px-3 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors"
            >
              {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              <span>{isPlaying ? 'Pause' : 'Play'}</span>
            </motion.button>

            {/* Removed standalone Transcribe button - live mode handles this */}

            {onVoiceInference && (
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => {
                  if (audioBlob) {
                    const audioFile = new File([audioBlob], 'recording.wav', { type: 'audio/wav' });
                    onVoiceInference(audioFile);
                  }
                }}
                className="flex items-center space-x-2 px-3 py-2 bg-purple-500 hover:bg-purple-600 text-white rounded-lg transition-colors"
              >
                <Brain className="h-4 w-4" />
                <span>Analyze Voice</span>
              </motion.button>
            )}

            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={deleteRecording}
              className="flex items-center space-x-2 px-3 py-2 bg-gray-500 hover:bg-gray-600 text-white rounded-lg transition-colors"
            >
              <Trash2 className="h-4 w-4" />
              <span>Delete</span>
            </motion.button>
          </div>
        )}
      </div>

      {/* Recording Status */}
      <AnimatePresence>
        {isRecording && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="flex items-center space-x-3 p-3 bg-red-50 border border-red-200 rounded-lg"
          >
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse"></div>
              <span className="text-sm font-medium text-red-800">Recording</span>
            </div>
            <div className="text-sm text-red-600 font-mono">
              {formatTime(recordingTime)}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Audio Player */}
      <AnimatePresence>
        {audioURL && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="p-3 bg-blue-50 border border-blue-200 rounded-lg"
          >
            <div className="flex items-center space-x-3">
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
                <span className="text-sm font-medium text-blue-800">Recording Ready</span>
              </div>
              <div className="text-sm text-blue-600 font-mono">
                {formatTime(recordingTime)}
              </div>
            </div>
            <audio
              ref={audioRef}
              src={audioURL}
              onEnded={() => setIsPlaying(false)}
              className="hidden"
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Transcript */}
      <AnimatePresence>
        {transcript && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="p-3 bg-green-50 border border-green-200 rounded-lg"
          >
            <div className="flex items-center space-x-2 mb-2">
              <div className="w-3 h-3 bg-green-500 rounded-full"></div>
              <span className="text-sm font-medium text-green-800">Transcription</span>
            </div>
            <p className="text-sm text-green-700">{transcript}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default VoiceRecorder;
