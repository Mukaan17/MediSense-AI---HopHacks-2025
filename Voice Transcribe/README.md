# Voice Transcription API with WhisperX & Live Recording

A FastAPI-based service that transcribes voice conversations between patients and doctors using WhisperX with advanced speaker diarization, generating structured JSON output with live audio recording capabilities.

## Features

- **WhisperX Integration**: Uses WhisperX with advanced speaker diarization for accurate speech-to-text conversion
- **Advanced Speaker Detection**: Automatic speaker identification using pyannote.audio diarization
- **Live Audio Recording**: Real-time audio capture and transcription from microphone
- **WebSocket Support**: Real-time audio streaming and processing
- **Structured Output**: Generates JSON in the exact format specified in your requirements
- **Enhanced Web Interface**: Tabbed interface with both file upload and live recording
- **Batch Processing**: Support for transcribing multiple audio files at once
- **Audio Preprocessing**: Optimizes audio files for better transcription accuracy
- **Alignment & Diarization**: Word-level alignment and speaker diarization for precise results

## Installation

1. **Clone or download the project files**

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install system dependencies**:
   - **macOS**: `brew install ffmpeg portaudio`
   - **Ubuntu/Debian**: `sudo apt update && sudo apt install ffmpeg portaudio19-dev`
   - **Windows**: Download ffmpeg and portaudio from their respective websites

4. **Set up Hugging Face token** (for pyannote.audio):
   ```bash
   # Optional: Create a Hugging Face account and get a token
   # The API will work without it, but with limited diarization features
   export HUGGINGFACE_HUB_TOKEN="your_token_here"
   ```

## Usage

### Starting the Server

```bash
python main.py
```

The API will be available at:
- **API**: http://localhost:8000
- **Web Interface**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

### Using the Web Interface

1. Open http://localhost:8000 in your browser
2. Choose between two modes:
   
   **File Upload Mode:**
   - Click "Choose File" and select an audio file
   - Optionally add a description of the conversation
   - Click "Transcribe Audio File"
   - View the formatted JSON output
   
   **Live Recording Mode:**
   - Click the "Live Recording" tab
   - Click "Start Recording" to begin capturing audio from your microphone
   - Speak your conversation (patient-doctor dialogue)
   - Click "Stop Recording" when finished
   - Click "Transcribe Recording" to process the audio
   - View the formatted JSON output with speaker identification

### API Endpoints

#### POST `/transcribe`
Transcribe a single audio file.

**Request**:
- `file`: Audio file (multipart/form-data)
- `description`: Optional description (form field)

**Response**:
```json
{
  "session_id": "uuid-string",
  "conversation": [
    {
      "description": "Patient with sore throat and cough...",
      "utterances": [
        {
          "speaker": "patient",
          "text": "My throat is sore and I have a cough",
          "timestamp": 0.0
        },
        {
          "speaker": "doctor", 
          "text": "I understand you have a sore throat...",
          "timestamp": 2.0
        }
      ]
    }
  ],
  "timestamp": "2024-01-01T12:00:00"
}
```

#### POST `/transcribe-batch`
Transcribe multiple audio files at once.

**Request**:
- `files`: Array of audio files (multipart/form-data)

**Response**:
Array of transcription responses (same format as single transcription).

#### POST `/start-live-recording`
Start a live recording session.

**Response**:
```json
{
  "session_id": "uuid-string",
  "status": "recording_started",
  "message": "Live recording started successfully"
}
```

#### POST `/stop-live-recording/{session_id}`
Stop live recording and return transcription.

**Response**:
Same format as `/transcribe` endpoint.

#### WebSocket `/ws/live-recording/{session_id}`
Real-time audio streaming endpoint for live transcription.

#### GET `/health`
Health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "whisperx_model_loaded": true,
  "diarization_model_loaded": true,
  "alignment_model_loaded": true,
  "active_sessions": 0
}
```

### Supported Audio Formats

- WAV
- MP3
- M4A
- FLAC
- OGG
- And other formats supported by FFmpeg

### Example Usage with curl

```bash
# Single file transcription
curl -X POST "http://localhost:8000/transcribe" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@conversation.wav" \
  -F "description=Patient consultation about cold symptoms"

# Batch transcription
curl -X POST "http://localhost:8000/transcribe-batch" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "files=@conversation1.wav" \
  -F "files=@conversation2.wav"
```

## Technical Details

### WhisperX Integration

The API now uses WhisperX which provides:
- **Advanced Speaker Diarization**: Uses pyannote.audio for accurate speaker identification
- **Word-level Alignment**: Precise timing and alignment of transcribed words
- **Better Accuracy**: Improved transcription quality over basic Whisper
- **Speaker Embeddings**: Advanced speaker recognition capabilities

### Speaker Detection

The implementation now uses proper speaker diarization:
- **pyannote.audio**: Advanced speaker diarization model
- **Speaker Embeddings**: Uses speaker voice characteristics for identification
- **Automatic Mapping**: Maps detected speakers to "patient" and "doctor" roles
- **Fallback**: Simple alternating pattern if diarization fails

### Audio Processing Pipeline

1. **Preprocessing**: Audio is normalized and resampled to 16kHz
2. **Transcription**: Uses WhisperX "base" model with alignment
3. **Diarization**: Speaker identification using pyannote.audio
4. **Alignment**: Word-level timing alignment
5. **Post-processing**: Text is segmented and formatted according to requirements

### Live Audio Recording

- **Real-time Capture**: Uses PyAudio for microphone input
- **WebSocket Support**: Real-time audio streaming capabilities
- **Browser Integration**: WebRTC-based recording in the browser
- **Session Management**: Tracks active recording sessions

### Model Selection

The API uses WhisperX "base" model by default. You can modify the model size in `main.py`:

- `tiny`: Fastest, least accurate
- `base`: Good balance (default)
- `small`: Better accuracy
- `medium`: High accuracy
- `large`: Best accuracy, slowest

## Customization

### Enhancing Speaker Detection

The API already includes advanced speaker diarization with pyannote.audio. To further enhance it:

1. **Get Hugging Face Token**: Sign up at https://huggingface.co and get an access token
2. **Set Environment Variable**: `export HUGGINGFACE_HUB_TOKEN="your_token"`
3. **Use Larger Models**: Modify the diarization model in `main.py` for better accuracy

### Custom Output Formatting

Modify the `format_conversation_output` function to change the JSON structure or add additional fields.

### Adding Authentication

For production use, consider adding:
- API key authentication
- Rate limiting
- User management
- Database storage for transcriptions

## Troubleshooting

### Common Issues

1. **"No module named 'torch'"**: Install PyTorch separately:
   ```bash
   pip install torch torchaudio
   ```

2. **"No module named 'pyaudio'"**: Install system dependencies:
   - **macOS**: `brew install portaudio`
   - **Ubuntu**: `sudo apt install portaudio19-dev`
   - **Windows**: Download from http://www.portaudio.com/

3. **WhisperX model loading errors**: Ensure you have sufficient disk space and memory:
   ```bash
   # Models are downloaded on first use
   # Base model: ~150MB, Small: ~500MB, Medium: ~1.5GB, Large: ~3GB
   ```

4. **Speaker diarization not working**: Check your Hugging Face token:
   ```bash
   export HUGGINGFACE_HUB_TOKEN="your_token_here"
   ```

5. **Microphone access denied**: Grant microphone permissions in your browser for live recording.

6. **Audio format not supported**: Ensure FFmpeg is installed and the audio file is in a supported format.

7. **Out of memory**: Use a smaller WhisperX model or process shorter audio files.

8. **Slow transcription**: The first request will be slower as models load. Subsequent requests will be faster.

### Performance Tips

- Use shorter audio files for faster processing
- Consider using the "tiny" model for real-time applications
- Implement caching for repeated transcriptions
- Use GPU acceleration if available (modify torch installation)
- For live recording, use shorter recording sessions for better responsiveness
- Enable browser microphone permissions for optimal live recording experience

## License

This project is provided as-is for educational and development purposes.

## Contributing

Feel free to submit issues and enhancement requests!
