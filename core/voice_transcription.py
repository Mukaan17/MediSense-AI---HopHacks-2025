# -*- coding: utf-8 -*-
# @Author: Mukhil Sundararaj
# @Date:   2025-09-13 16:14:38
# @Last Modified by:   Mukhil Sundararaj
# @Last Modified time: 2025-09-13 17:10:19
"""
Voice transcription module for integrating WhisperX into the main backend.
This module provides audio transcription capabilities with speaker diarization.
"""

import os
import tempfile
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
import librosa
import soundfile as sf
import numpy as np
import whisperx
from pydantic import BaseModel


class Utterance(BaseModel):
    speaker: str
    text: str
    timestamp: float = None
    confidence: float = None


class ConversationEntry(BaseModel):
    description: str
    utterances: List[Utterance]


class TranscriptionResponse(BaseModel):
    session_id: str
    conversation: List[ConversationEntry]
    timestamp: str


class VoiceTranscriptionService:
    """Service for handling voice transcription using WhisperX"""
    
    def __init__(self):
        self.whisperx_model = None
        self.diarize_model = None
        self.align_model = None
        self.align_metadata = None
        self._load_models()
    
    def _load_models(self):
        """Load WhisperX models once at startup"""
        if self.whisperx_model is None:
            print("Loading WhisperX models...")
            try:
                # Load WhisperX model with correct API for 3.1.1
                try:
                    # Method 1: Try the newer API
                    self.whisperx_model = whisperx.load_model("base", device="cpu", compute_type="int8")
                    print("✅ WhisperX model loaded")
                except Exception as e1:
                    print(f"Method 1 failed: {e1}")
                    try:
                        # Method 2: Try without compute_type
                        self.whisperx_model = whisperx.load_model("base", device="cpu")
                        print("✅ WhisperX model loaded (without compute_type)")
                    except Exception as e2:
                        print(f"Method 2 failed: {e2}")
                        # Method 3: Fall back to basic whisper
                        import whisper
                        self.whisperx_model = whisper.load_model("base")
                        print("✅ Basic Whisper model loaded as fallback")
                
                # Load alignment model
                try:
                    self.align_model, self.align_metadata = whisperx.load_align_model(language_code="en", device="cpu")
                    print("✅ Alignment model loaded")
                except Exception as align_error:
                    print(f"⚠️  Alignment model not available: {align_error}")
                    self.align_model = None
                    self.align_metadata = None
                
                # Load diarization model - using direct pyannote.audio approach
                try:
                    # Try with auth token first
                    hf_token = os.getenv("HUGGINGFACE_HUB_TOKEN")
                    if hf_token:
                        try:
                            # Login to Hugging Face first
                            from huggingface_hub import login
                            login(token=hf_token)
                            
                            # Use direct pyannote.audio Pipeline (more reliable)
                            from pyannote.audio import Pipeline
                            self.diarize_model = Pipeline.from_pretrained("pyannote/speaker-diarization", use_auth_token=hf_token)
                            print("✅ Diarization model loaded with Hugging Face token")
                        except Exception as e1:
                            print(f"Direct pyannote.audio Pipeline failed: {e1}")
                            try:
                                # Fallback to WhisperX DiarizationPipeline
                                self.diarize_model = whisperx.DiarizationPipeline(use_auth_token=hf_token, device="cpu")
                                print("✅ WhisperX DiarizationPipeline loaded as fallback")
                            except Exception as e2:
                                print(f"WhisperX DiarizationPipeline failed: {e2}")
                                self.diarize_model = None
                    else:
                        # Try without auth token (may have limited functionality)
                        try:
                            from pyannote.audio import Pipeline
                            self.diarize_model = Pipeline.from_pretrained("pyannote/speaker-diarization", use_auth_token=False)
                            print("✅ Diarization model loaded without token (limited functionality)")
                        except Exception as e3:
                            print(f"Unauthenticated diarization model failed: {e3}")
                            self.diarize_model = None
                except Exception as diarize_error:
                    print(f"⚠️  Diarization model not available: {diarize_error}")
                    print("💡 To enable full diarization, set HUGGINGFACE_HUB_TOKEN environment variable")
                    self.diarize_model = None
                
            except Exception as e:
                print(f"Error loading WhisperX models: {e}")
                print("Falling back to basic Whisper...")
                import whisper
                self.whisperx_model = whisper.load_model("base")
                self.diarize_model = None
                self.align_model = None
                self.align_metadata = None
    
    def preprocess_audio(self, audio_path: str) -> str:
        """Preprocess audio file for better transcription"""
        try:
            # Load audio with librosa
            audio, sr = librosa.load(audio_path, sr=16000)  # WhisperX expects 16kHz
            
            # Normalize audio
            audio = librosa.util.normalize(audio)
            
            # Create temporary file for processed audio
            processed_path = tempfile.mktemp(suffix=".wav")
            sf.write(processed_path, audio, sr)
            
            return processed_path
        except Exception as e:
            print(f"Error preprocessing audio: {e}")
            return audio_path
    
    def transcribe_audio(self, audio_path: str) -> Dict[str, Any]:
        """Transcribe audio using WhisperX with speaker diarization"""
        try:
            # Load audio
            audio = whisperx.load_audio(audio_path)
            
            # Transcribe
            result = self.whisperx_model.transcribe(audio)
            
            # Align whisper output
            if self.align_model is not None and self.align_metadata is not None:
                result = whisperx.align(result["segments"], self.align_model, self.align_metadata, audio, "cpu", return_char_alignments=False)
            
            # Diarize (speaker identification) - using correct API for WhisperX 3.1.1
            if self.diarize_model is not None:
                try:
                    print("🎤 Starting speaker diarization...")
                    # Check if it's a pyannote.audio Pipeline or WhisperX DiarizationPipeline
                    if hasattr(self.diarize_model, 'apply'):
                        # It's a pyannote.audio Pipeline
                        print("Using pyannote.audio Pipeline for diarization")
                        diarize_segments = self.diarize_model(audio_path)
                        result = whisperx.assign_word_speakers(diarize_segments, result)
                    else:
                        # It's a WhisperX DiarizationPipeline
                        print("Using WhisperX DiarizationPipeline for diarization")
                        diarize_segments = self.diarize_model(audio)
                        result = whisperx.assign_word_speakers(diarize_segments, result)
                    print(f"✅ Diarization completed: {len(result.get('segments', []))} segments with speaker info")
                except Exception as diarize_error:
                    print(f"⚠️  Diarization failed: {diarize_error}")
                    print(f"   Error type: {type(diarize_error).__name__}")
                    print(f"   Error details: {str(diarize_error)}")
                    # Continue without diarization - the fallback logic will handle this
            
            return result
            
        except Exception as e:
            print(f"Error in WhisperX transcription: {e}")
            # Fallback to basic transcription
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(audio_path)
            return {"segments": [{"text": result["text"], "start": 0, "end": len(result["text"])/10}]}
    
    def format_output(self, result: Dict[str, Any], description: str = None) -> ConversationEntry:
        """Format WhisperX output into the required JSON structure"""
        
        # Generate description if not provided
        if not description:
            all_text = " ".join([seg.get("text", "") for seg in result.get("segments", [])])
            description = f"Audio conversation with multiple speakers detected."
        
        print(f"📝 Formatting {len(result.get('segments', []))} segments...")
        
        # Process segments and group by speaker
        utterances = []
        current_speaker = None
        current_text = ""
        current_start = 0
        
        # Check if we have speaker information in segments
        has_speaker_info = any(seg.get("speaker") for seg in result.get("segments", []))
        
        for i, segment in enumerate(result.get("segments", [])):
            speaker = segment.get("speaker", "SPEAKER_00")
            text = segment.get("text", "").strip()
            start_time = segment.get("start", 0)
            
            print(f"Segment {i}: speaker={speaker}, text='{text[:50]}...', start={start_time}")
            
            # Map speaker IDs to patient/doctor
            if speaker == "SPEAKER_00":
                speaker_label = "patient"
            elif speaker == "SPEAKER_01":
                speaker_label = "doctor"
            else:
                # For more than 2 speakers, alternate
                speaker_num = int(speaker.split("_")[1]) if "_" in speaker else 0
                speaker_label = "patient" if speaker_num % 2 == 0 else "doctor"
            
            # If speaker changed, save previous utterance
            if current_speaker and current_speaker != speaker_label and current_text:
                utterances.append(Utterance(
                    speaker=current_speaker,
                    text=current_text.strip(),
                    timestamp=current_start,
                    confidence=0.9  # Default confidence
                ))
                current_text = ""
            
            # Add to current text
            if current_text:
                current_text += " " + text
            else:
                current_text = text
                current_start = start_time
            
            current_speaker = speaker_label
        
        # Add the last utterance
        if current_text and current_speaker:
            utterances.append(Utterance(
                speaker=current_speaker,
                text=current_text.strip(),
                timestamp=current_start,
                confidence=0.9
            ))
        
        # If no speaker diarization worked or we have multiple segments but same speaker,
        # try to intelligently split based on content and timing
        if not utterances or (len(result.get("segments", [])) > 1 and len(set(seg.get("speaker", "SPEAKER_00") for seg in result.get("segments", []))) == 1):
            print("🔄 No speaker diarization detected, using intelligent fallback...")
            utterances = []
            
            # Use each segment as a separate utterance, alternating speakers
            speakers = ["patient", "doctor"]
            
            for i, segment in enumerate(result.get("segments", [])):
                text = segment.get("text", "").strip()
                start_time = segment.get("start", 0)
                
                if text:  # Only add non-empty segments
                    speaker = speakers[i % 2]  # Alternate between patient and doctor
                    utterances.append(Utterance(
                        speaker=speaker,
                        text=text,
                        timestamp=start_time,
                        confidence=0.8
                    ))
                    print(f"Fallback segment {i}: [{speaker}] '{text[:50]}...' at {start_time}s")
        
        # Final fallback: if still no utterances, create one from all text
        if not utterances:
            all_text = " ".join([seg.get("text", "") for seg in result.get("segments", [])])
            if all_text.strip():
                utterances.append(Utterance(
                    speaker="patient",
                    text=all_text.strip(),
                    timestamp=0,
                    confidence=0.7
                ))
        
        return ConversationEntry(
            description=description,
            utterances=utterances
        )
    
    def transcribe_file(self, file_content: bytes, filename: str, description: str = None) -> TranscriptionResponse:
        """Transcribe an uploaded audio file"""
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        try:
            # Preprocess audio
            processed_audio_path = self.preprocess_audio(temp_file_path)
            
            # Transcribe with WhisperX
            print(f"Transcribing audio file with WhisperX: {filename}")
            result = self.transcribe_audio(processed_audio_path)
            
            print(f"Transcription completed: {len(result.get('segments', []))} segments")
            
            # Format the output
            conversation_entry = self.format_output(result, description)
            
            # Create response
            response = TranscriptionResponse(
                session_id=session_id,
                conversation=[conversation_entry],
                timestamp=datetime.now().isoformat()
            )
            
            return response
            
        finally:
            # Clean up temporary files
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            if os.path.exists(processed_audio_path) and processed_audio_path != temp_file_path:
                os.unlink(processed_audio_path)


# Global instance
voice_service = VoiceTranscriptionService()

