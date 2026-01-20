#!/usr/bin/env python3
"""
Quick Fix & Run Script
Installs missing dependencies and runs the system
"""

import subprocess
import sys
import os

def run_command(cmd, check=True):
    """Run a command and return success"""
    try:
        result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def main():
    print("🔧 Fixing dependencies and starting system...")
    print("")
    
    # Check if we're in venv
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    
    if not in_venv:
        print("⚠️  Not in virtual environment. Activating .venv...")
        venv_path = os.path.join(os.path.dirname(__file__), '.venv', 'bin', 'activate')
        if os.path.exists(venv_path):
            print("✅ Found .venv, activating...")
        else:
            print("❌ No .venv found. Creating one...")
            success, _, _ = run_command("python3 -m venv .venv", check=False)
            if not success:
                print("❌ Failed to create venv")
                return
    
    # Install critical dependencies first
    print("📦 Installing critical dependencies...")
    critical_packages = [
        "numpy>=1.24.0",
        "pandas>=2.0.0",
        "anthropic>=0.34.0",
        "openai>=1.0.0",
        "requests>=2.31.0",
        "python-dotenv>=1.0.0"
    ]
    
    for package in critical_packages:
        print(f"  Installing {package}...")
        success, stdout, stderr = run_command(f"pip install {package}", check=False)
        if not success:
            print(f"  ⚠️  Warning: {package} installation had issues")
            if stderr:
                print(f"     {stderr[:200]}")
        else:
            print(f"  ✅ {package} installed")
    
    # Verify installation
    print("")
    print("🔍 Verifying installation...")
    test_imports = [
        "numpy",
        "pandas", 
        "anthropic",
        "openai"
    ]
    
    all_good = True
    for module in test_imports:
        success, _, _ = run_command(f"python3 -c 'import {module}'", check=False)
        if success:
            print(f"  ✅ {module} - OK")
        else:
            print(f"  ❌ {module} - FAILED")
            all_good = False
    
    if not all_good:
        print("")
        print("❌ Some dependencies failed. Trying pip install -r requirements.txt...")
        run_command("pip install -r requirements.txt", check=False)
    
    print("")
    print("🚀 Starting Elite Quant Trading System...")
    print("")
    
    # Run main.py
    os.system("python3 main.py")

if __name__ == "__main__":
    main()
