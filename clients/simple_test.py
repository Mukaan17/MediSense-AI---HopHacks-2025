# -*- coding: utf-8 -*-
# @Author: Mukhil Sundararaj
# @Date:   2025-09-13 15:56:20
# @Last Modified by:   Mukhil Sundararaj
# @Last Modified time: 2025-09-13 16:06:24
#!/usr/bin/env python3
"""
Simple test client for the multimodal clinical reference system.
Tests image-only functionality without requiring LLM API keys.
"""

import requests
import json
import sys

def test_image_only():
    """Test image-only inference endpoint."""
    print("Testing image-only inference...")
    
    url = "http://localhost:8000/image_infer"
    image_path = sys.argv[1] if len(sys.argv) > 1 else "train/patient00005/study1/view1_frontal.jpg"
    
    try:
        with open(image_path, "rb") as f:
            files = {"file": (image_path, f, "image/jpeg")}
            response = requests.post(url, files=files, timeout=30)
            
        if response.status_code == 200:
            result = response.json()
            print("✓ Image inference successful!")
            print(f"Filename: {result.get('filename')}")
            print("Top findings:")
            for i, finding in enumerate(result.get('image_findings', [])[:5]):
                print(f"  {i+1}. {finding['label']}: {finding['score']:.3f}")
            return True
        else:
            print(f"✗ Error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ Exception: {e}")
        return False

def test_health():
    """Test health endpoint."""
    print("Testing health endpoint...")
    
    try:
        response = requests.get("http://localhost:8000/health", timeout=10)
        if response.status_code == 200:
            result = response.json()
            print("✓ Health check successful!")
            print(f"Status: {result.get('status')}")
            print(f"Document count: {result.get('doc_count')}")
            print(f"EHR loaded: {result.get('ehr_loaded')}")
            return True
        else:
            print(f"✗ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Health check exception: {e}")
        return False

if __name__ == "__main__":
    print("=== Multimodal Clinical Reference System Test ===")
    print()
    
    # Test health first
    health_ok = test_health()
    print()
    
    if health_ok:
        # Test image inference
        image_ok = test_image_only()
        print()
        
        if image_ok:
            print("✓ All basic tests passed!")
            print()
            print("Next steps:")
            print("1. Set your GROQ_API_KEY in the .env file")
            print("2. Restart the server: python -m uvicorn api.server:app --host 0.0.0.0 --port 8000")
            print("3. Test full multimodal functionality with: python clients/live_client.py")
        else:
            print("✗ Image inference test failed")
    else:
        print("✗ Health check failed - server may not be running")
        print("Start the server with: python -m uvicorn api.server:app --host 0.0.0.0 --port 8000")
