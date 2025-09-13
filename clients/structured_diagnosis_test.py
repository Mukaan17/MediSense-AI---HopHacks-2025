#!/usr/bin/env python3
"""
Test client for the new structured differential diagnosis endpoint
"""

import json
import requests
from typing import Dict, Any

# Server configuration
BASE_URL = "http://localhost:8000"

def test_structured_diagnosis():
    """Test the structured diagnosis endpoint"""
    
    # Test case 1: Hypertension with EHR data
    print("=== Test Case 1: Hypertension with EHR Data ===")
    
    payload = {
        "utterances": [
            "Patient presents with severe headache for 3 days",
            "Blood pressure is 178/108",
            "No chest pain or shortness of breath",
            "Patient is 65-year-old male with history of hypertension",
            "Currently taking lisinopril 10mg daily"
        ],
        "patient_id": "P001"  # This should match an EHR patient
    }
    
    response = requests.post(
        f"{BASE_URL}/structured_diagnosis",
        data={"payload": json.dumps(payload)}
    )
    
    if response.status_code == 200:
        result = response.json()
        print("✅ Structured Diagnosis Response:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
    
    print("\n" + "="*80 + "\n")
    
    # Test case 2: Chest pain scenario
    print("=== Test Case 2: Chest Pain Scenario ===")
    
    payload2 = {
        "utterances": [
            "Patient complains of crushing chest pain",
            "Pain radiates to left arm",
            "Started 2 hours ago",
            "Patient is 58-year-old male",
            "History of diabetes and smoking"
        ]
    }
    
    response2 = requests.post(
        f"{BASE_URL}/structured_diagnosis",
        data={"payload": json.dumps(payload2)}
    )
    
    if response2.status_code == 200:
        result2 = response2.json()
        print("✅ Structured Diagnosis Response:")
        print(json.dumps(result2, indent=2, ensure_ascii=False))
    else:
        print(f"❌ Error: {response2.status_code} - {response2.text}")

def test_ehr_integration():
    """Test EHR integration endpoints"""
    
    print("=== Testing EHR Integration ===")
    
    # List all patients
    print("1. Listing all EHR patients...")
    response = requests.get(f"{BASE_URL}/ehr/patients")
    if response.status_code == 200:
        patients = response.json()
        print(f"✅ Found {patients['total']} patients")
        for patient in patients['patients'][:3]:  # Show first 3
            print(f"   - {patient['patient_id']}: {patient['demographics']['age']}y {patient['demographics']['sex']}")
    else:
        print(f"❌ Error listing patients: {response.status_code}")
    
    # Get specific patient
    print("\n2. Getting specific patient data...")
    response = requests.get(f"{BASE_URL}/ehr/patients/P001")
    if response.status_code == 200:
        patient = response.json()
        print("✅ Patient P001 data:")
        print(json.dumps(patient, indent=2, ensure_ascii=False))
    else:
        print(f"❌ Error getting patient: {response.status_code}")
    
    # Mock import patient data
    print("\n3. Testing patient data import (mockup)...")
    import_data = {
        "demographics": {"age": 45, "sex": "F"},
        "vital_signs": {"bp": "140/90", "hr": 85},
        "pmh": ["hypertension"],
        "meds": ["amlodipine"],
        "allergies": ["penicillin"]
    }
    
    response = requests.post(
        f"{BASE_URL}/ehr/import_patient_data",
        data={
            "patient_id": "TEST001",
            "payload": json.dumps(import_data)
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        print("✅ Import successful:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"❌ Error importing: {response.status_code}")

def test_health_endpoint():
    """Test the health endpoint to ensure server is running"""
    print("=== Testing Health Endpoint ===")
    
    response = requests.get(f"{BASE_URL}/health")
    if response.status_code == 200:
        health = response.json()
        print("✅ Server is healthy:")
        print(f"   - Status: {health['status']}")
        print(f"   - EHR loaded: {health['ehr_loaded']} records")
        print(f"   - Doc count: {health['doc_count']}")
        return True
    else:
        print(f"❌ Server health check failed: {response.status_code}")
        return False

def main():
    """Main test function"""
    print("🧪 Testing Structured Differential Diagnosis System")
    print("="*60)
    
    # Check if server is running
    if not test_health_endpoint():
        print("\n❌ Server is not running. Please start the server first:")
        print("   uvicorn api.server:app --host 0.0.0.0 --port 8000")
        return
    
    print("\n" + "="*60)
    
    # Test structured diagnosis
    test_structured_diagnosis()
    
    # Test EHR integration
    test_ehr_integration()
    
    print("\n🎉 Testing completed!")

if __name__ == "__main__":
    main()
