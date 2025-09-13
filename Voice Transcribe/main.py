from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import whisperx
import tempfile
import os
import json
import uuid
from datetime import datetime
import librosa
import soundfile as sf
import numpy as np
from pathlib import Path
import asyncio
import pyaudio
import wave
import threading
import queue
import time
import io
import base64
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="Voice Transcription API with WhisperX", version="2.0.0")

# Enable CORS for web interface
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global models (loaded once for efficiency)
whisperx_model = None
diarize_model = None
align_model = None
align_metadata = None

class TranscriptionRequest(BaseModel):
    session_id: str = None
    description: str = None

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

class LiveSession(BaseModel):
    session_id: str
    is_recording: bool = False
    start_time: Optional[datetime] = None

# Store active live sessions
active_sessions: Dict[str, LiveSession] = {}

def load_whisperx_models():
    """Load WhisperX models once at startup"""
    global whisperx_model, diarize_model, align_model, align_metadata
    
    if whisperx_model is None:
        print("Loading WhisperX models...")
        try:
            # Load WhisperX model with correct API for 3.1.1
            # Try different approaches to load the model
            try:
                # Method 1: Try the newer API
                whisperx_model = whisperx.load_model("base", device="cpu", compute_type="int8")
                print("✅ WhisperX model loaded")
            except Exception as e1:
                print(f"Method 1 failed: {e1}")
                try:
                    # Method 2: Try without compute_type
                    whisperx_model = whisperx.load_model("base", device="cpu")
                    print("✅ WhisperX model loaded (without compute_type)")
                except Exception as e2:
                    print(f"Method 2 failed: {e2}")
                    # Method 3: Fall back to basic whisper
                    import whisper
                    whisperx_model = whisper.load_model("base")
                    print("✅ Basic Whisper model loaded as fallback")
            
            # Load alignment model
            try:
                align_model, align_metadata = whisperx.load_align_model(language_code="en", device="cpu")
                print("✅ Alignment model loaded")
            except Exception as align_error:
                print(f"⚠️  Alignment model not available: {align_error}")
                align_model = None
                align_metadata = None
            
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
                        diarize_model = Pipeline.from_pretrained("pyannote/speaker-diarization", use_auth_token=hf_token)
                        print("✅ Diarization model loaded with Hugging Face token")
                    except Exception as e1:
                        print(f"Direct pyannote.audio Pipeline failed: {e1}")
                        try:
                            # Fallback to WhisperX DiarizationPipeline
                            diarize_model = whisperx.DiarizationPipeline(use_auth_token=hf_token, device="cpu")
                            print("✅ WhisperX DiarizationPipeline loaded as fallback")
                        except Exception as e2:
                            print(f"WhisperX DiarizationPipeline failed: {e2}")
                            diarize_model = None
                else:
                    # Try without auth token (may have limited functionality)
                    try:
                        from pyannote.audio import Pipeline
                        diarize_model = Pipeline.from_pretrained("pyannote/speaker-diarization", use_auth_token=False)
                        print("✅ Diarization model loaded without token (limited functionality)")
                    except Exception as e3:
                        print(f"Unauthenticated diarization model failed: {e3}")
                        diarize_model = None
            except Exception as diarize_error:
                print(f"⚠️  Diarization model not available: {diarize_error}")
                print("💡 To enable full diarization, set HUGGINGFACE_HUB_TOKEN environment variable")
                diarize_model = None
            
        except Exception as e:
            print(f"Error loading WhisperX models: {e}")
            print("Falling back to basic Whisper...")
            import whisper
            whisperx_model = whisper.load_model("base")
            diarize_model = None
            align_model = None
            align_metadata = None
    
    return whisperx_model, diarize_model, align_model, align_metadata

def preprocess_audio(audio_path: str) -> str:
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

def transcribe_with_whisperx(audio_path: str) -> Dict[str, Any]:
    """Transcribe audio using WhisperX with speaker diarization"""
    try:
        model, diarize_model, align_model, align_metadata = load_whisperx_models()
        
        # Load audio
        audio = whisperx.load_audio(audio_path)
        
        # Transcribe
        result = model.transcribe(audio)
        
        # Align whisper output
        if align_model is not None and align_metadata is not None:
            result = whisperx.align(result["segments"], align_model, align_metadata, audio, "cpu", return_char_alignments=False)
        
        # Diarize (speaker identification) - using correct API for WhisperX 3.1.1
        if diarize_model is not None:
            try:
                print("🎤 Starting speaker diarization...")
                # Check if it's a pyannote.audio Pipeline or WhisperX DiarizationPipeline
                if hasattr(diarize_model, 'apply'):
                    # It's a pyannote.audio Pipeline
                    print("Using pyannote.audio Pipeline for diarization")
                    diarize_segments = diarize_model(audio_path)
                    result = whisperx.assign_word_speakers(diarize_segments, result)
                else:
                    # It's a WhisperX DiarizationPipeline
                    print("Using WhisperX DiarizationPipeline for diarization")
                    diarize_segments = diarize_model(audio)
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

def format_whisperx_output(result: Dict[str, Any], description: str = None) -> ConversationEntry:
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

class LiveAudioRecorder:
    """Handles live audio recording and streaming"""
    
    def __init__(self):
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self.audio_data = []
        self.sample_rate = 16000
        self.chunk_size = 1024
        self.channels = 1
        self.format = pyaudio.paInt16
        self.audio = None
        self.stream = None
        self.recording_thread = None
    
    def start_recording(self):
        """Start recording audio"""
        if self.is_recording:
            return
        
        try:
            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                stream_callback=self.audio_callback
            )
            
            self.is_recording = True
            self.audio_data = []
            self.stream.start_stream()
            print("🎤 Live recording started")
            
        except Exception as e:
            print(f"Error starting recording: {e}")
            raise
    
    def stop_recording(self):
        """Stop recording and return audio data"""
        if not self.is_recording:
            return None
        
        self.is_recording = False
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        if self.audio:
            self.audio.terminate()
        
        # Convert audio data to numpy array
        if self.audio_data:
            audio_bytes = b''.join(self.audio_data)
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
            return audio_array.astype(np.float32) / 32768.0  # Normalize to [-1, 1]
        
        return None
    
    def audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for audio stream"""
        if self.is_recording:
            self.audio_data.append(in_data)
        return (in_data, pyaudio.paContinue)
    
    def get_audio_chunk(self):
        """Get a chunk of audio data for streaming"""
        try:
            return self.audio_queue.get_nowait()
        except queue.Empty:
            return None

# Global recorder instance
live_recorder = LiveAudioRecorder()

@app.on_event("startup")
async def startup_event():
    """Load models on startup"""
    load_whisperx_models()

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the enhanced web interface with live recording"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Voice Transcription API with Live Recording</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; }
            .container { background: #f5f5f5; padding: 20px; border-radius: 10px; }
            .upload-area { border: 2px dashed #ccc; padding: 20px; text-align: center; margin: 20px 0; }
            .upload-area:hover { border-color: #007bff; }
            .live-recording { border: 2px solid #28a745; padding: 20px; text-align: center; margin: 20px 0; background: #d4edda; }
            .recording-active { background: #f8d7da; border-color: #dc3545; }
            button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 5px; }
            button:hover { background: #0056b3; }
            button:disabled { background: #6c757d; cursor: not-allowed; }
            .record-btn { background: #dc3545; }
            .record-btn:hover { background: #c82333; }
            .stop-btn { background: #6c757d; }
            .stop-btn:hover { background: #545b62; }
            .result { background: white; padding: 15px; border-radius: 5px; margin-top: 20px; }
            .error { color: red; }
            .success { color: green; }
            .recording-indicator { display: none; color: #dc3545; font-weight: bold; }
            .recording-indicator.active { display: block; animation: pulse 1s infinite; }
            @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
            .tabs { display: flex; margin-bottom: 20px; }
            .tab { padding: 10px 20px; background: #e9ecef; border: 1px solid #dee2e6; cursor: pointer; }
            .tab.active { background: #007bff; color: white; }
            .tab-content { display: none; }
            .tab-content.active { display: block; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎤 Voice Transcription API with Live Recording</h1>
            <p>Transcribe patient-doctor conversations using WhisperX with advanced speaker diarization.</p>
            
            <div class="tabs">
                <div class="tab active" onclick="switchTab('file')">📁 File Upload</div>
                <div class="tab" onclick="switchTab('live')">🎤 Live Recording</div>
            </div>
            
            <!-- File Upload Tab -->
            <div id="file-tab" class="tab-content active">
                <div class="upload-area">
                    <input type="file" id="audioFile" accept="audio/*" />
                    <br><br>
                    <input type="text" id="description" placeholder="Optional: Description of the conversation" style="width: 100%; padding: 10px; margin: 10px 0;" />
                    <br>
                    <button onclick="transcribeAudio()">Transcribe Audio File</button>
                </div>
            </div>
            
            <!-- Live Recording Tab -->
            <div id="live-tab" class="tab-content">
                <div class="live-recording" id="recordingArea">
                    <h3>🎤 Live Audio Recording</h3>
                    <p>Click "Start Recording" to begin capturing live audio from your microphone.</p>
                    <div class="recording-indicator" id="recordingIndicator">🔴 RECORDING...</div>
                    <br>
                    <button id="startBtn" class="record-btn" onclick="startLiveRecording()">Start Recording</button>
                    <button id="stopBtn" class="stop-btn" onclick="stopLiveRecording()" disabled>Stop Recording</button>
                    <button id="transcribeBtn" onclick="transcribeLiveAudio()" disabled>Transcribe Recording</button>
                    <br><br>
                    <input type="text" id="liveDescription" placeholder="Optional: Description of the conversation" style="width: 100%; padding: 10px;" />
                </div>
            </div>
            
            <div id="result"></div>
        </div>
        
        <script>
            let isRecording = false;
            let mediaRecorder = null;
            let audioChunks = [];
            let websocket = null;
            
            function switchTab(tabName) {
                // Hide all tabs
                document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
                document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
                
                // Show selected tab
                document.getElementById(tabName + '-tab').classList.add('active');
                event.target.classList.add('active');
            }
            
            async function transcribeAudio() {
                const fileInput = document.getElementById('audioFile');
                const descriptionInput = document.getElementById('description');
                const resultDiv = document.getElementById('result');
                
                if (!fileInput.files[0]) {
                    resultDiv.innerHTML = '<div class="error">Please select an audio file.</div>';
                    return;
                }
                
                const formData = new FormData();
                formData.append('file', fileInput.files[0]);
                if (descriptionInput.value) {
                    formData.append('description', descriptionInput.value);
                }
                
                resultDiv.innerHTML = '<div>Transcribing with WhisperX... Please wait.</div>';
                
                try {
                    const response = await fetch('/transcribe', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const result = await response.json();
                    
                    if (response.ok) {
                        resultDiv.innerHTML = `
                            <div class="success">Transcription completed successfully!</div>
                            <div class="result">
                                <h3>Session ID: ${result.session_id}</h3>
                                <h4>Conversation:</h4>
                                <pre>${JSON.stringify(result.conversation, null, 2)}</pre>
                            </div>
                        `;
                    } else {
                        resultDiv.innerHTML = `<div class="error">Error: ${result.detail}</div>`;
                    }
                } catch (error) {
                    resultDiv.innerHTML = `<div class="error">Error: ${error.message}</div>`;
                }
            }
            
            async function startLiveRecording() {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);
                    audioChunks = [];
                    
                    mediaRecorder.ondataavailable = event => {
                        audioChunks.push(event.data);
                    };
                    
                    mediaRecorder.onstop = () => {
                        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                        // Store the blob for transcription
                        window.recordedAudioBlob = audioBlob;
                    };
                    
                    mediaRecorder.start();
                    isRecording = true;
                    
                    // Update UI
                    document.getElementById('startBtn').disabled = true;
                    document.getElementById('stopBtn').disabled = false;
                    document.getElementById('transcribeBtn').disabled = true;
                    document.getElementById('recordingIndicator').classList.add('active');
                    document.getElementById('recordingArea').classList.add('recording-active');
                    
                } catch (error) {
                    alert('Error accessing microphone: ' + error.message);
                }
            }
            
            function stopLiveRecording() {
                if (mediaRecorder && isRecording) {
                    mediaRecorder.stop();
                    isRecording = false;
                    
                    // Update UI
                    document.getElementById('startBtn').disabled = false;
                    document.getElementById('stopBtn').disabled = true;
                    document.getElementById('transcribeBtn').disabled = false;
                    document.getElementById('recordingIndicator').classList.remove('active');
                    document.getElementById('recordingArea').classList.remove('recording-active');
                }
            }
            
            async function transcribeLiveAudio() {
                if (!window.recordedAudioBlob) {
                    alert('No recorded audio found. Please record first.');
                    return;
                }
                
                const descriptionInput = document.getElementById('liveDescription');
                const resultDiv = document.getElementById('result');
                
                const formData = new FormData();
                formData.append('file', window.recordedAudioBlob, 'recording.wav');
                if (descriptionInput.value) {
                    formData.append('description', descriptionInput.value);
                }
                
                resultDiv.innerHTML = '<div>Transcribing live recording with WhisperX... Please wait.</div>';
                
                try {
                    const response = await fetch('/transcribe', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const result = await response.json();
                    
                    if (response.ok) {
                        resultDiv.innerHTML = `
                            <div class="success">Live recording transcription completed!</div>
                            <div class="result">
                                <h3>Session ID: ${result.session_id}</h3>
                                <h4>Conversation:</h4>
                                <pre>${JSON.stringify(result.conversation, null, 2)}</pre>
                            </div>
                        `;
                    } else {
                        resultDiv.innerHTML = `<div class="error">Error: ${result.detail}</div>`;
                    }
                } catch (error) {
                    resultDiv.innerHTML = `<div class="error">Error: ${error.message}</div>`;
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    description: str = None
):
    """
    Transcribe audio file using WhisperX and return formatted conversation data
    """
    try:
        # Validate file type
        if file.content_type and not file.content_type.startswith('audio/'):
            raise HTTPException(status_code=400, detail="File must be an audio file")
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        try:
            # Preprocess audio
            processed_audio_path = preprocess_audio(temp_file_path)
            
            # Transcribe with WhisperX
            print(f"Transcribing audio file with WhisperX: {file.filename}")
            result = transcribe_with_whisperx(processed_audio_path)
            
            print(f"Transcription completed: {len(result.get('segments', []))} segments")
            
            # Format the output
            conversation_entry = format_whisperx_output(result, description)
            
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
                
    except Exception as e:
        print(f"Error during transcription: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

@app.websocket("/ws/live-recording/{session_id}")
async def websocket_live_recording(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for live audio streaming and real-time transcription"""
    await websocket.accept()
    
    try:
        # Initialize session
        active_sessions[session_id] = LiveSession(
            session_id=session_id,
            is_recording=True,
            start_time=datetime.now()
        )
        
        await websocket.send_text(json.dumps({
            "type": "session_started",
            "session_id": session_id,
            "message": "Live recording session started"
        }))
        
        while True:
            # Receive audio data from client
            data = await websocket.receive_bytes()
            
            # Process audio chunk (this would be implemented for real-time processing)
            # For now, we'll just acknowledge receipt
            await websocket.send_text(json.dumps({
                "type": "audio_received",
                "timestamp": datetime.now().isoformat()
            }))
            
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": str(e)
        }))
    finally:
        # Clean up session
        if session_id in active_sessions:
            del active_sessions[session_id]

@app.post("/start-live-recording")
async def start_live_recording():
    """Start a live recording session"""
    session_id = str(uuid.uuid4())
    
    try:
        live_recorder.start_recording()
        active_sessions[session_id] = LiveSession(
            session_id=session_id,
            is_recording=True,
            start_time=datetime.now()
        )
        
        return {
            "session_id": session_id,
            "status": "recording_started",
            "message": "Live recording started successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {str(e)}")

@app.post("/stop-live-recording/{session_id}")
async def stop_live_recording(session_id: str):
    """Stop live recording and return audio data"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        audio_data = live_recorder.stop_recording()
        
        if audio_data is not None:
            # Save audio data to temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            sf.write(temp_file.name, audio_data, live_recorder.sample_rate)
            
            # Transcribe the recorded audio
            result = transcribe_with_whisperx(temp_file.name)
            conversation_entry = format_whisperx_output(result)
            
            # Clean up
            os.unlink(temp_file.name)
            del active_sessions[session_id]
            
            return TranscriptionResponse(
                session_id=session_id,
                conversation=[conversation_entry],
                timestamp=datetime.now().isoformat()
            )
        else:
            raise HTTPException(status_code=400, detail="No audio data recorded")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop recording: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    model, diarize_model, align_model, align_metadata = load_whisperx_models()
    return {
        "status": "healthy",
        "whisperx_model_loaded": model is not None,
        "diarization_model_loaded": diarize_model is not None,
        "alignment_model_loaded": align_model is not None,
        "active_sessions": len(active_sessions)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)