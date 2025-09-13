# -*- coding: utf-8 -*-
# @Author: Mukhil Sundararaj
# @Date:   2025-09-13 16:16:18
# @Last Modified by:   Mukhil Sundararaj
# @Last Modified time: 2025-09-13 17:10:23
#!/usr/bin/env python3
"""
Startup script for the integrated voice transcription backend
"""

import uvicorn
import sys
import os
from pathlib import Path

def main():
    """Run the integrated FastAPI server with voice transcription"""
    print("🚀 Starting Integrated Voice Transcription Backend...")
    print("=" * 60)
    
    # Check if we're in the right directory
    if not Path("api/server.py").exists():
        print("❌ Error: api/server.py not found")
        print("   Please run this script from the project root directory")
        sys.exit(1)
    
    # Check if requirements are installed
    try:
        import whisperx
        import librosa
        import soundfile
        print("✅ Voice transcription dependencies found")
    except ImportError as e:
        print(f"❌ Missing dependencies: {e}")
        print("   Please install requirements: pip install -r requirements.txt")
        sys.exit(1)
    
    print("📋 Server Configuration:")
    print("   - API Server: http://localhost:8000")
    print("   - API Documentation: http://localhost:8000/docs")
    print("   - Health Check: http://localhost:8000/health")
    print("   - Voice Transcription: Integrated")
    print("   - Clinical Analysis: Enabled")
    print("   - Multimodal Support: Voice + Image + Text")
    print()
    print("🎤 Available Endpoints:")
    print("   - POST /voice_transcribe - Transcribe audio files")
    print("   - POST /voice_infer - Voice-based clinical inference")
    print("   - POST /multimodal_voice_infer - Voice + image inference")
    print("   - POST /infer - Text-based inference (existing)")
    print("   - POST /multimodal_infer - Text + image inference (existing)")
    print()
    print("💡 Tips:")
    print("   - First startup will download WhisperX models (~150MB)")
    print("   - Set HUGGINGFACE_HUB_TOKEN for enhanced speaker diarization")
    print("   - Test with: python test_voice_integration.py")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    
    try:
        uvicorn.run(
            "api.server:app",
            host="0.0.0.0",
            port=8000,
            reload=False,  # Disable auto-reload to prevent constant restarts
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

