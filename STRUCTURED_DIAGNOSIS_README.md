# Enhanced Structured Differential Diagnosis System

This document describes the new structured differential diagnosis features integrated into the clinical RAG system.

## 🎯 Overview

The enhanced system provides:
- **Structured Differential Diagnosis** with top 3 ranked diagnoses
- **Risk Factor Analysis** based on patient demographics, vitals, and history
- **Enhanced Red Flag Alerts** with severity levels and time sensitivity
- **EHR Integration** with clinical workflow actions and order suggestions
- **Clinical Decision Support** with evidence-based reasoning

## 🏗️ Architecture

### New Modules

1. **`core/clinical_diagnosis.py`** - Main diagnosis engine
2. **`core/ehr_integration.py`** - EHR workflow integration
3. **`config/prompts/structured_diagnosis.j2`** - Enhanced prompt template

### Enhanced Endpoints

- **`/structured_diagnosis`** - New structured diagnosis endpoint
- **`/ehr/patients`** - List EHR patients
- **`/ehr/patients/{patient_id}`** - Get specific patient data
- **`/ehr/import_patient_data`** - Import patient data (mockup)
- **`/ehr/export_clinical_summary`** - Export clinical summary (mockup)

## 📊 Structured Output Format

### Differential Diagnosis Structure

```json
{
  "differential_diagnosis": {
    "top_3_diagnoses": [
      {
        "condition": "hypertension_uncontrolled",
        "confidence": 0.85,
        "likelihood": "high",
        "supporting_evidence": [
          "BP 178/108",
          "Headache for 3 days",
          "No antihypertensive medications"
        ],
        "risk_factors": [
          {
            "factor": "age",
            "value": "65",
            "risk_level": "moderate",
            "description": "Advanced age increases risk for multiple conditions"
          }
        ],
        "ruling_out_evidence": [
          "No chest pain",
          "No neurological deficits"
        ],
        "next_steps": [
          "Immediate BP recheck",
          "ECG to rule out cardiac complications",
          "Basic metabolic panel"
        ]
      }
    ],
    "red_flag_alerts": [
      {
        "alert_type": "critical",
        "condition": "hypertensive_crisis",
        "urgency": "immediate",
        "message": "BP 178/108 suggests hypertensive crisis - immediate attention required",
        "action_required": "Consider emergency evaluation",
        "time_sensitivity": "within 1 hour"
      }
    ],
    "risk_assessment": {
      "overall_risk_level": "high",
      "primary_concerns": ["cardiovascular", "neurological"],
      "monitoring_required": ["vital_signs", "neurological_exam"]
    }
  }
}
```

### Clinical Workflow Integration

```json
{
  "clinical_workflow": {
    "ehr_actions": [
      {
        "action": "add_to_problem_list",
        "condition": "hypertension_uncontrolled",
        "priority": "high",
        "icd10_code": "I10"
      }
    ],
    "order_suggestions": [
      {
        "order_type": "lab",
        "test": "Basic Metabolic Panel",
        "urgency": "routine",
        "reasoning": "Baseline renal function before antihypertensive adjustment"
      }
    ],
    "follow_up_plan": [
      {
        "timeline": "1 week",
        "reason": "Monitor blood pressure response to treatment",
        "actions": ["Blood pressure recheck", "Assess medication adherence"]
      }
    ]
  }
}
```

## 🚀 Usage Examples

### Basic Structured Diagnosis

```python
import requests
import json

payload = {
    "utterances": [
        "Patient presents with severe headache for 3 days",
        "Blood pressure is 178/108",
        "No chest pain or shortness of breath"
    ],
    "patient_id": "P001"  # Optional EHR patient ID
}

response = requests.post(
    "http://localhost:8000/structured_diagnosis",
    data={"payload": json.dumps(payload)}
)

result = response.json()
print(json.dumps(result, indent=2))
```

### With Image Analysis

```python
# Include image file in the request
files = {"file": open("chest_xray.jpg", "rb")}
data = {"payload": json.dumps(payload)}

response = requests.post(
    "http://localhost:8000/structured_diagnosis",
    data=data,
    files=files
)
```

### EHR Integration

```python
# List all patients
patients = requests.get("http://localhost:8000/ehr/patients").json()

# Get specific patient
patient = requests.get("http://localhost:8000/ehr/patients/P001").json()

# Import patient data (mockup)
import_data = {
    "demographics": {"age": 45, "sex": "F"},
    "vital_signs": {"bp": "140/90", "hr": 85},
    "pmh": ["hypertension"],
    "meds": ["amlodipine"]
}

response = requests.post(
    "http://localhost:8000/ehr/import_patient_data",
    data={
        "patient_id": "NEW001",
        "payload": json.dumps(import_data)
    }
)
```

## 🧪 Testing

Run the test client to verify functionality:

```bash
python clients/structured_diagnosis_test.py
```

This will test:
- Structured diagnosis endpoint
- EHR integration endpoints
- Patient data import/export
- Health checks

## 🔧 Configuration

### Environment Variables

```bash
# Existing variables
export EHR_JSON="ehr_with_images.json"
export RAG_PERSIST_DIR=./rag_store
export RAG_COLLECTION=conversations
export GROQ_API_KEY=your_key_here

# New variables for structured diagnosis
export ASK_THRESH=0.70          # Confidence threshold for questions
export MARGIN_THRESH=0.08       # Margin threshold for questions
export MAX_CTX_CHARS=4000       # Max context characters
```

### Prompt Customization

Edit `config/prompts/structured_diagnosis.j2` to customize:
- Output format
- Clinical reasoning approach
- Risk assessment criteria
- Red flag definitions

## 🏥 Clinical Features

### Risk Factor Analysis

The system automatically analyzes:
- **Age-based risks** (65+ = moderate risk, 50+ = low risk)
- **Gender-based risks** (male = cardiovascular risk)
- **Vital signs risks** (BP, HR, temp, SpO2)
- **Past medical history** (diabetes, hypertension, etc.)
- **Social history** (smoking, alcohol use)

### Red Flag Detection

Critical alerts for:
- **Hypertensive crisis** (BP ≥180/110)
- **Severe tachycardia** (HR >120)
- **Hypoxia** (SpO2 <90%)
- **High fever** (temp >103°F)
- **Stroke symptoms** (neurological deficits)
- **Chest pain** (crushing, radiating)
- **Respiratory distress** (severe SOB)

### Clinical Workflow Integration

- **Problem list management** with ICD-10 codes
- **Order suggestions** (labs, imaging, procedures)
- **Follow-up planning** with timelines
- **Medication alerts** for interactions
- **Documentation notes** for clinical records

## 🔮 Future Enhancements

### Planned Features

1. **Real EHR Integration**
   - Epic FHIR API integration
   - Cerner API integration
   - HL7 message handling

2. **Advanced Analytics**
   - Population health insights
   - Risk stratification models
   - Outcome prediction

3. **Clinical Decision Support**
   - Treatment pathway recommendations
   - Drug interaction checking
   - Clinical guideline integration

4. **Quality Metrics**
   - Diagnostic accuracy tracking
   - Clinical outcome monitoring
   - Performance analytics

## 📚 API Documentation

### Structured Diagnosis Endpoint

**POST** `/structured_diagnosis`

**Request:**
```json
{
  "utterances": ["Patient complaint 1", "Patient complaint 2"],
  "patient_id": "P001"  // Optional
}
```

**Response:**
```json
{
  "structured_diagnosis": { /* differential diagnosis structure */ },
  "risk_analysis": { /* risk factors and alerts */ },
  "ehr_integration": { /* workflow actions */ },
  "fusion": { /* existing fusion results */ },
  "coach": { /* suggested questions */ }
}
```

### EHR Integration Endpoints

- **GET** `/ehr/patients` - List all patients
- **GET** `/ehr/patients/{patient_id}` - Get patient data
- **POST** `/ehr/import_patient_data` - Import patient data
- **POST** `/ehr/export_clinical_summary` - Export clinical summary

## 🛡️ Safety & Compliance

### Clinical Safety

- **Advisory-only language** - No diagnostic claims
- **Evidence-based reasoning** - All recommendations backed by context
- **Conservative approach** - Err on side of caution for red flags
- **Human oversight** - All recommendations require clinician review

### Data Privacy

- **HIPAA compliance** - Patient data handling
- **Secure transmission** - HTTPS/TLS encryption
- **Access controls** - Authentication and authorization
- **Audit logging** - Track all clinical decisions

## 🤝 Contributing

To contribute to the structured diagnosis system:

1. **Add new risk factors** in `clinical_diagnosis.py`
2. **Enhance red flag detection** with new clinical criteria
3. **Improve EHR integration** with additional workflow actions
4. **Update prompts** for better clinical reasoning
5. **Add tests** for new functionality

## 📞 Support

For questions or issues with the structured diagnosis system:

1. Check the test client output
2. Review server logs for errors
3. Verify EHR data format
4. Test with simple cases first
5. Contact the development team

---

**Note**: This system is designed for clinical decision support and should always be used in conjunction with clinical judgment and appropriate medical oversight.
