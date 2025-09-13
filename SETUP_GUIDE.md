# Multimodal Clinical Reference System - Local Setup Guide

This guide helps you set up and run the multimodal clinical reference system locally with CPU-only inference.

## ✅ Completed Setup

The following components have been successfully set up:

1. **Virtual Environment**: Created `.venv` with CPU-only PyTorch
2. **Dependencies**: All required packages installed
3. **Configuration**: `.env` file created with local settings
4. **Knowledge Base**: Built from `English Train.json` (643 chunks indexed)
5. **Imaging Model**: BiomedCLIP checkpoint loaded and tested
6. **Server**: FastAPI server configured and running
7. **Test Client**: Basic functionality verified

## 🚀 Quick Start

### 1. Activate Environment
```bash
source .venv/bin/activate
```

### 2. Set Your API Key
Edit `.env` file and replace `YOUR_GROQ_KEY_HERE` with your actual Groq API key:
```bash
GROQ_API_KEY=your_actual_groq_api_key_here
```

Get a free API key from: https://console.groq.com/

### 3. Start the Server
```bash
python -m uvicorn api.server:app --host 0.0.0.0 --port 8000
```

### 4. Test the System
```bash
# Basic functionality test
python clients/simple_test.py

# Live transcribing simulation
python clients/live_client.py
```

## 📊 System Status

- **Server**: Running on http://localhost:8000
- **Health Check**: http://localhost:8000/health
- **API Docs**: http://localhost:8000/docs
- **Knowledge Base**: 643 documents indexed
- **EHR Records**: 14 records loaded
- **Imaging Model**: BiomedCLIP (CPU-only)

## 🔧 Available Endpoints

- `GET /health` - System health check
- `POST /image_infer` - Image-only analysis
- `POST /infer` - Conversation-only analysis
- `POST /multimodal_infer` - Combined image + conversation
- `POST /infer_from_image_only` - Image with EHR matching

## 🧪 Smoke Tests

### A) Image Only
```bash
curl -s -X POST "http://localhost:8000/image_infer" \
  -F "file=@train/patient00005/study1/view1_frontal.jpg" | jq
```

### B) Conversation Only
```bash
curl -s -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"utterances":["patient: bp 178/108 last night and headache","doctor: any weakness or chest pain?","patient: no chest pain, a bit dizzy"]}' | jq
```

### C) Multimodal (conversation + image)
```bash
curl -s -X POST "http://localhost:8000/multimodal_infer" \
  -F 'payload={"utterances":["patient: cough + fever 2 days","doctor: any dyspnea?","patient: mild dyspnea"]}' \
  -F "file=@train/patient00005/study1/view1_frontal.jpg" | jq
```

## 🎯 Live Transcribing

The system is ready for live transcribing integration. The `clients/live_client.py` demonstrates how to:

1. Poll the `/multimodal_infer` endpoint every 2-3 seconds
2. Send growing transcripts as conversation progresses
3. Receive real-time clinical insights and clarifying questions

To integrate with real ASR:
- Replace the simulated utterances in `live_client.py` with your ASR stream
- Keep calling the same `/multimodal_infer` endpoint
- The system will provide evolving clinical assessments

## 🔍 Configuration

Key settings in `.env`:

```bash
# Imaging
CXR_CKPT=checkpoints/biovil_vit_chexpert.pt
CXR_DEVICE=cpu
CXR_TOPK=6

# RAG
RAG_PERSIST_DIR=./rag_store
RAG_COLLECTION=conversations
RAG_EMB_MODEL=sentence-transformers/all-MiniLM-L6-v2

# LLM
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.1-70b-versatile

# Question thresholds
ASK_THRESH=0.70      # Ask questions if confidence < 70%
MARGIN_THRESH=0.08   # Ask if margin between top 2 < 8%
```

## 🐛 Troubleshooting

### Server won't start
- Check if port 8000 is available
- Verify all dependencies are installed: `pip list`
- Check `.env` file exists and has correct paths

### API errors
- Ensure GROQ_API_KEY is set correctly
- Check server logs for detailed error messages
- Test with `python clients/simple_test.py` first

### Model loading issues
- Verify checkpoint file exists: `ls -la checkpoints/`
- Check available memory (models are large)
- CPU-only inference may be slower than GPU

## 📁 Project Structure

```
HopHacks/
├── api/server.py              # FastAPI server
├── core/                      # Core components
│   ├── imaging.py            # BiomedCLIP model
│   ├── retriever.py          # RAG retrieval
│   ├── fusion.py             # Multimodal fusion
│   └── ...
├── clients/                   # Test clients
│   ├── simple_test.py        # Basic functionality test
│   └── live_client.py        # Live transcribing demo
├── rag_store/                 # Vector database
├── checkpoints/               # Model checkpoints
├── .env                       # Configuration
└── English Train.json         # Training data
```

## 🎉 Success!

Your multimodal clinical reference system is now running locally with:
- ✅ CPU-only inference
- ✅ Real-time image analysis
- ✅ RAG-powered clinical insights
- ✅ Live transcribing capability
- ✅ EHR integration
- ✅ Confidence-based question generation

Ready for live transcribing integration!
