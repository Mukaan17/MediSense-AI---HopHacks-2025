#!/usr/bin/env python3
"""
Simple script to run the Voice Transcription API server
"""

import uvicorn
import sys
import os

def main():
    """Run the FastAPI server"""
    print("Starting Voice Transcription API...")
    print("Server will be available at: http://localhost:8000")
    print("Web interface: http://localhost:8000")
    print("API docs: http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop the server")
    
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,  # Auto-reload on code changes
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
