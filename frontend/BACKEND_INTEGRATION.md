# Backend Integration Guide

This document explains how to integrate the frontend with the backend API.

## 🚀 Quick Start

1. **Start the backend server** on port 8000
2. **Start the frontend**:
   ```bash
   npm start
   ```
3. **Open** http://localhost:3000

## 🔌 API Endpoints

The frontend expects the following backend endpoints:

### Core Endpoints (Currently Implemented)

#### `GET /health`
Health check endpoint
```json
{
  "status": "ok",
  "collection": "conversations",
  "persist_dir": "./rag_store",
  "emb_model": "sentence-transformers/all-mpnet-base-v2",
  "top_k": 5,
  "doc_count": 150
}
```

#### `POST /infer`
Text-based inference
```json
// Request
{
  "utterances": ["Patient reports chest pain", "BP 140/90"]
}

// Response
{
  "extraction": {
    "extracted": {
      "chief_complaint": "Chest pain",
      "symptoms": ["chest pain", "elevated blood pressure"],
      "duration": "2 hours",
      "possible_pmh": ["hypertension"],
      "possible_meds": ["lisinopril"]
    },
    "retrieval_query": "chest pain elevated blood pressure"
  },
  "answer": {
    "potential_issues_ranked": [
      {
        "condition": "hypertension_uncontrolled",
        "why": "Elevated blood pressure with associated symptoms",
        "confidence": 0.78
      }
    ],
    "red_flags_to_screen": ["Chest pain with radiation"],
    "first_steps_non_prescriptive": [
      "Immediate vital signs assessment",
      "ECG to rule out cardiac involvement"
    ],
    "follow_up": "Return in 1 week for re-evaluation",
    "citations": ["Mayo Clinic Guidelines §Chest Pain"]
  }
}
```

#### `POST /image_infer`
Image analysis
```json
// Request: multipart/form-data with 'file' field

// Response
{
  "image_findings": [
    {
      "label": "chest_xray_normal",
      "prob": 0.85,
      "description": "Normal chest X-ray appearance"
    }
  ]
}
```

#### `POST /multimodal_infer`
Combined text and image analysis
```json
// Request: multipart/form-data
// - payload: JSON string with utterances, patient, mode
// - file: image file (optional)

// Response
{
  "image_findings": [...],
  "text_findings": [...],
  "domains": {
    "cardiac": ["hypertension_uncontrolled"],
    "pulmonary": []
  },
  "fusion": {
    "top10": [
      {
        "condition": "hypertension_uncontrolled",
        "score": 0.78,
        "why": "Combined evidence from symptoms and imaging"
      }
    ],
    "final_suggested_issue": {...}
  },
  "rag_advisory": "Patient presents with chest pain and elevated blood pressure..."
}
```

### Future Endpoints (Ready for Implementation)

#### `POST /quick_entry`
Structured input processing
```json
// Request
{
  "symptoms": ["chest pain", "shortness of breath"],
  "vitals": {
    "bloodPressure": {"systolic": 140, "diastolic": 90},
    "heartRate": 85
  },
  "patient": {
    "age": 45,
    "gender": "male"
  },
  "voice_note": "audio file (optional)"
}
```

#### `POST /ehr/import_patient`
EHR integration
```json
// Request
{
  "patient_id": "12345",
  "ehr_system": "epic"
}

// Response
{
  "status": "success",
  "imported_data": {
    "demographics": {...},
    "vitals": {...},
    "medications": [...],
    "allergies": [...],
    "history": [...]
  }
}
```

#### `GET /ehr/export_report`
Export clinical report
```json
// Request: ?session_id=123

// Response
{
  "report": "PDF/HL7 format",
  "ready": true
}
```

#### `GET /knowledge_base/mode`
Get current knowledge base mode
```json
{
  "mode": "clinical",
  "sources": ["Clinical Guidelines", "UpToDate"],
  "lastUpdated": "2024-01-15T10:00:00Z"
}
```

#### `POST /knowledge_base/mode`
Set knowledge base mode
```json
// Request
{
  "mode": "research"
}

// Response
{
  "mode": "research",
  "sources": ["PubMed", "Cochrane Reviews"],
  "lastUpdated": "2024-01-20T10:00:00Z"
}
```

#### `POST /voice/transcribe`
Voice transcription
```json
// Request: multipart/form-data with 'audio' field

// Response
{
  "transcript": "Patient reports chest pain and shortness of breath...",
  "confidence": 0.95
}
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the frontend root:

```env
# Backend API Configuration
REACT_APP_API_URL=http://localhost:8000

# Development Settings
REACT_APP_DEBUG=true
REACT_APP_LOG_LEVEL=info

# Feature Flags
REACT_APP_ENABLE_VOICE_RECORDING=true
REACT_APP_ENABLE_IMAGE_UPLOAD=true
REACT_APP_ENABLE_EHR_INTEGRATION=true
```

### API Configuration

The frontend uses the configuration in `src/config/api.ts`:

```typescript
export const API_CONFIG = {
  BASE_URL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
  TIMEOUT: 30000,
  RETRY_ATTEMPTS: 3,
  RETRY_DELAY: 1000,
};
```

## 📊 Data Flow

### 1. Patient Input
- User fills patient form (demographics, vitals, history)
- Data stored in React state

### 2. Clinical Notes
- Text input via textarea
- Voice recording via microphone
- Quick entry via dropdowns

### 3. Image Upload
- Drag & drop or file picker
- Supports JPEG, PNG, GIF, BMP, TIFF

### 4. Analysis Request
- Frontend sends multimodal request to backend
- Includes patient data, symptoms, and optional image

### 5. Response Processing
- Backend returns structured analysis
- Frontend processes into clinical report format
- Displays in organized UI components

## 🎯 Frontend Components

### Core Components
- **ClinicalInterface**: Main application interface
- **PatientForm**: Patient data input
- **VoiceRecorder**: Voice note recording
- **XAIExplanation**: Explainable AI display
- **DifferentialDiagnosis**: Diagnosis results
- **RedFlagAlerts**: Safety alerts
- **ClinicalReportView**: Report viewer
- **EHRIntegration**: EHR mockups
- **KnowledgeBaseToggle**: Mode switching

### Data Types
All TypeScript interfaces are defined in `src/types/index.ts`:
- `Patient`: Patient demographics and history
- `ClinicalReport`: Complete clinical analysis
- `DifferentialDiagnosis`: Diagnosis with confidence
- `RedFlagAlert`: Safety alerts
- `XAIExplanation`: AI reasoning and sources

## 🚨 Error Handling

The frontend includes comprehensive error handling:

1. **Network Errors**: Connection timeouts, server unavailable
2. **API Errors**: Invalid responses, authentication failures
3. **Validation Errors**: Missing required fields, invalid data
4. **User Feedback**: Toast notifications for all error states

## 🔍 Debugging

### Console Logging
- All API requests/responses are logged
- Health check status on startup
- Error details for troubleshooting

### Development Tools
- React Developer Tools
- Network tab for API monitoring
- Console for error inspection

## 🚀 Deployment

### Production Build
```bash
npm run build
```

### Environment Setup
```bash
# Production
REACT_APP_API_URL=https://your-backend-api.com

# Staging
REACT_APP_API_URL=https://staging-api.com
```

### Static Hosting
The build folder can be deployed to:
- Vercel
- Netlify
- AWS S3
- GitHub Pages

## 🔄 Backend Integration Checklist

- [ ] Backend server running on port 8000
- [ ] `/health` endpoint responding
- [ ] `/infer` endpoint implemented
- [ ] `/image_infer` endpoint implemented
- [ ] `/multimodal_infer` endpoint implemented
- [ ] CORS configured for frontend domain
- [ ] Error responses in expected format
- [ ] Response data matches frontend expectations

## 📞 Support

For integration issues:
1. Check browser console for errors
2. Verify backend server is running
3. Test API endpoints directly
4. Check network tab for failed requests
5. Review backend logs for errors
