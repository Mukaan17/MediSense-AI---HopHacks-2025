# Frontend-Backend Integration Guide

This document describes the complete integration between the React frontend and FastAPI backend for the Clinical AI Assistant.

## 🚀 Quick Start

### 1. Start the Backend
```bash
# From project root
python run_integrated_server.py
```

### 2. Start the Frontend
```bash
# In a new terminal
cd frontend
npm install
npm start
```

### 3. Test Integration
```bash
# From project root
python test_integration.py
```

## 🔗 API Integration Overview

### Backend Endpoints (FastAPI)

| Endpoint | Method | Purpose | Frontend Usage |
|----------|--------|---------|----------------|
| `/health` | GET | Health check | App initialization |
| `/infer` | POST | Text-only inference | Quick analysis |
| `/multimodal_infer` | POST | Text + image inference | Multimodal analysis |
| `/structured_diagnosis` | POST | Structured diagnosis | Comprehensive analysis |
| `/voice_transcribe` | POST | Voice transcription | Voice notes |
| `/voice_infer` | POST | Voice-only inference | Voice analysis |
| `/multimodal_voice_infer` | POST | Voice + image inference | Complete voice workflow |
| `/ehr/patients` | GET | List EHR patients | Patient selection |
| `/ehr/patients/{id}` | GET | Get specific patient | Patient details |
| `/ehr/import_patient_data` | POST | Import patient data | EHR integration |
| `/ehr/export_clinical_summary` | POST | Export clinical report | Report export |

### Frontend Components

| Component | Purpose | Backend Integration |
|-----------|---------|-------------------|
| `ClinicalInterface` | Main interface | All inference endpoints |
| `VoiceRecorder` | Voice recording/transcription | Voice endpoints |
| `PatientForm` | Patient data entry | EHR patient selection |
| `EHRIntegration` | EHR import/export | EHR endpoints |
| `DifferentialDiagnosis` | Display diagnoses | Structured diagnosis data |
| `RedFlagAlerts` | Show alerts | Risk analysis data |

## 🎯 Key Features Integrated

### 1. Voice Processing
- **Real-time recording** with browser MediaRecorder API
- **WhisperX transcription** via backend
- **Voice-based inference** for direct clinical analysis
- **Multimodal voice** (voice + image) analysis

### 2. Image Analysis
- **Drag & drop upload** with react-dropzone
- **Multiple formats** (JPEG, PNG, GIF, BMP, TIFF)
- **BioViL model** integration for medical imaging
- **Combined with text/voice** for multimodal analysis

### 3. Structured Diagnosis
- **Comprehensive analysis** with risk factors and red flags
- **Evidence-based reasoning** with confidence scores
- **Clinical guidelines** integration
- **EHR context** incorporation

### 4. EHR Integration
- **Patient selection** from existing EHR data
- **Import/export** functionality (mockup for Epic/Cerner)
- **Patient demographics** and medical history
- **Clinical report** export to EHR systems

### 5. Real-time Analysis
- **Quick analysis** for immediate insights
- **Structured diagnosis** for comprehensive evaluation
- **Confidence scoring** and uncertainty handling
- **Live question generation** for low-confidence cases

## 📊 Data Flow

### Text Analysis Flow
```
User Input → ClinicalInterface → clinicalAPI.infer() → Backend /infer → 
Extraction → Retrieval → Answer Generation → Frontend Display
```

### Voice Analysis Flow
```
Voice Recording → VoiceRecorder → clinicalAPI.voiceInfer() → Backend /voice_infer → 
Transcription → Extraction → Retrieval → Answer Generation → Frontend Display
```

### Multimodal Analysis Flow
```
Text + Image → ClinicalInterface → clinicalAPI.multimodalInfer() → Backend /multimodal_infer → 
Image Analysis + Text Extraction → Fusion → Retrieval → Answer Generation → Frontend Display
```

### Structured Diagnosis Flow
```
Input → ClinicalInterface → clinicalAPI.structuredDiagnosis() → Backend /structured_diagnosis → 
Comprehensive Analysis → Risk Assessment → Red Flag Detection → Structured Report → Frontend Display
```

## 🔧 Configuration

### Backend Configuration
```bash
# Environment variables
export EHR_JSON="ehr_with_images.json"
export RAG_PERSIST_DIR=./rag_store
export RAG_COLLECTION=conversations
export RAG_EMB_MODEL=sentence-transformers/all-mpnet-base-v2
export GROQ_API_KEY=your_groq_key
export GROQ_MODEL=llama-3.1-70b-versatile
export ASK_THRESH=0.70
export MARGIN_THRESH=0.08
```

### Frontend Configuration
```bash
# Environment variables
export REACT_APP_API_URL=http://localhost:8000
export REACT_APP_ENABLE_VOICE_RECORDING=true
export REACT_APP_ENABLE_IMAGE_UPLOAD=true
export REACT_APP_ENABLE_EHR_INTEGRATION=true
```

## 🧪 Testing

### Backend Testing
```bash
# Test individual endpoints
curl -X GET http://localhost:8000/health
curl -X POST http://localhost:8000/infer -H "Content-Type: application/json" -d '{"utterances": ["chest pain"]}'
```

### Frontend Testing
```bash
# Run integration tests
python test_integration.py

# Manual testing
# 1. Open http://localhost:3000
# 2. Test voice recording
# 3. Test image upload
# 4. Test patient selection
# 5. Test analysis buttons
```

## 🐛 Troubleshooting

### Common Issues

1. **Backend Connection Failed**
   - Check if backend is running on port 8000
   - Verify environment variables are set
   - Check firewall settings

2. **Voice Recording Not Working**
   - Ensure microphone permissions are granted
   - Check browser compatibility (Chrome/Firefox recommended)
   - Verify audio format support

3. **Image Upload Issues**
   - Check file format (JPEG, PNG, GIF, BMP, TIFF)
   - Verify file size limits
   - Check network connectivity

4. **EHR Integration Problems**
   - Ensure EHR JSON file exists
   - Check patient data format
   - Verify API endpoint responses

### Debug Mode
```bash
# Enable debug logging
export REACT_APP_DEBUG=true
export REACT_APP_LOG_LEVEL=debug
```

## 📈 Performance Considerations

### Backend Optimization
- **Model caching** for faster inference
- **Async processing** for voice transcription
- **Connection pooling** for database queries
- **Response compression** for large payloads

### Frontend Optimization
- **Lazy loading** for components
- **Memoization** for expensive calculations
- **Debounced API calls** for real-time features
- **Progressive loading** for large datasets

## 🔒 Security Considerations

### API Security
- **Input validation** on all endpoints
- **Rate limiting** for API calls
- **CORS configuration** for cross-origin requests
- **Authentication** for production deployment

### Data Privacy
- **Local processing** for sensitive data
- **Encryption** for data transmission
- **Audit logging** for clinical decisions
- **HIPAA compliance** considerations

## 🚀 Deployment

### Production Build
```bash
# Backend
pip install -r requirements.txt
python run_integrated_server.py

# Frontend
cd frontend
npm run build
# Serve build/ directory with nginx or similar
```

### Docker Deployment
```bash
# Build and run with Docker Compose
docker-compose up --build
```

## 📚 Additional Resources

- [Backend API Documentation](http://localhost:8000/docs)
- [Frontend Component Library](./frontend/src/components/)
- [Voice Integration Guide](./VOICE_INTEGRATION_README.md)
- [Structured Diagnosis Guide](./STRUCTURED_DIAGNOSIS_README.md)
- [Setup Guide](./SETUP_GUIDE.md)

## 🤝 Contributing

1. **Backend Changes**: Update API endpoints and test with frontend
2. **Frontend Changes**: Update API calls and test with backend
3. **Integration Changes**: Test both systems together
4. **Documentation**: Update this guide for any changes

## 📞 Support

For integration issues:
1. Check the troubleshooting section
2. Run the integration test script
3. Review the console logs
4. Check the network tab in browser dev tools
