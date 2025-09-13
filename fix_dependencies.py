# -*- coding: utf-8 -*-
# @Author: Mukhil Sundararaj
# @Date:   2025-09-13 16:30:34
# @Last Modified by:   Mukhil Sundararaj
# @Last Modified time: 2025-09-13 16:32:15
#!/usr/bin/env python3
"""
Fix dependency conflicts by uninstalling conflicting packages and reinstalling compatible versions
"""

import subprocess
import sys

def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(f"✅ {description} completed")
            return True
        else:
            print(f"❌ {description} failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"⏰ {description} timed out")
        return False
    except Exception as e:
        print(f"❌ {description} error: {e}")
        return False

def main():
    print("🚀 Fixing dependency conflicts...")
    
    # Step 1: Uninstall conflicting packages
    packages_to_remove = [
        "protobuf",
        "tensorflow", 
        "tf-keras",
        "tensorboard"
    ]
    
    for package in packages_to_remove:
        run_command(f"pip uninstall -y {package}", f"Uninstalling {package}")
    
    # Step 2: Install compatible versions
    compatible_versions = [
        "protobuf>=3.20.2,<5.0.0",
        "tensorflow>=2.10.0,<2.17.0", 
        "tf-keras>=2.10.0,<2.17.0"
    ]
    
    for package in compatible_versions:
        run_command(f"pip install '{package}'", f"Installing {package}")
    
    # Step 3: Install other required packages
    other_packages = [
        "langchain-groq==0.3.8",
        "sentence-transformers==2.2.2"
    ]
    
    for package in other_packages:
        run_command(f"pip install {package}", f"Installing {package}")
    
    print("🎉 Dependency fix completed!")
    
    # Step 4: Test imports
    print("🧪 Testing imports...")
    test_imports = [
        "import tensorflow as tf",
        "import protobuf", 
        "from core.clinical_diagnosis import generate_structured_differential_diagnosis",
        "from core.ehr_integration import create_ehr_integration_summary"
    ]
    
    for test_import in test_imports:
        try:
            exec(test_import)
            print(f"✅ {test_import}")
        except Exception as e:
            print(f"❌ {test_import}: {e}")

if __name__ == "__main__":
    main()
