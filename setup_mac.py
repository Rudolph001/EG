#!/usr/bin/env python3
"""
Mac setup script for Email Guardian
Run this script to set up the application for local development on macOS
"""

import os
import sys
import subprocess
import sqlite3
from pathlib import Path

def check_homebrew():
    """Check if Homebrew is installed"""
    try:
        subprocess.check_output(['which', 'brew'])
        print("✓ Homebrew is installed")
        return True
    except subprocess.CalledProcessError:
        print("✗ Homebrew not found")
        print("Installing Homebrew...")
        try:
            subprocess.check_call([
                '/bin/bash', '-c', 
                'curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh'
            ])
            print("✓ Homebrew installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to install Homebrew: {e}")
            print("Please install Homebrew manually: https://brew.sh")
            return False

def install_system_dependencies():
    """Install system dependencies via Homebrew"""
    print("Installing system dependencies...")
    dependencies = ['python3', 'postgresql', 'sqlite3']
    
    for dep in dependencies:
        try:
            subprocess.check_call(['brew', 'install', dep])
            print(f"✓ {dep} installed")
        except subprocess.CalledProcessError:
            print(f"⚠ {dep} might already be installed or failed to install")

def install_python_dependencies():
    """Install Python dependencies"""
    print("Installing Python dependencies...")
    try:
        # Use python3 explicitly on Mac
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✓ Python dependencies installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install dependencies: {e}")
        print("Try running with sudo if permissions are needed:")
        print("sudo python3 -m pip install -r requirements.txt")
        sys.exit(1)

def create_directories():
    """Create necessary directories with proper Mac permissions"""
    print("Creating necessary directories...")
    directories = ['uploads', 'data', 'instance', 'static/css', 'static/js', 'templates']
    
    for directory in directories:
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        # Set Mac-friendly permissions
        os.chmod(str(dir_path), 0o755)
    
    print("✓ Directories created with proper permissions")

def setup_database():
    """Initialize SQLite database for Mac"""
    print("Setting up SQLite database...")
    db_path = "instance/email_guardian.db"
    
    # Create instance directory if it doesn't exist
    instance_dir = Path("instance")
    instance_dir.mkdir(exist_ok=True)
    os.chmod(str(instance_dir), 0o755)
    
    # Create empty database file if it doesn't exist
    if not os.path.exists(db_path):
        Path(db_path).touch()
        os.chmod(db_path, 0o664)
    
    print("✓ Database setup complete")

def create_env_file():
    """Create a local .env file for Mac"""
    print("Creating local environment file...")
    
    env_content = """# Email Guardian Mac Configuration
FLASK_ENV=development
FLASK_DEBUG=true
SESSION_SECRET=local-dev-secret-key-change-in-production-mac
DATABASE_URL=sqlite:///instance/email_guardian.db
FAST_MODE=true
CHUNK_SIZE=1000
MAX_ML_RECORDS=5000
PYTHONPATH=${PYTHONPATH}:.
"""
    
    # Create .env file for local development
    with open(".env.mac", "w") as f:
        f.write(env_content)
    
    print("✓ Mac environment file created (.env.mac)")

def setup_basic_config():
    """Run basic configuration setup"""
    print("Setting up basic configuration...")
    try:
        subprocess.check_call([sys.executable, "setup_basic_config.py"])
        print("✓ Basic configuration setup complete")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to setup basic configuration: {e}")
        print("You can run 'python3 setup_basic_config.py' manually later")

def create_launch_scripts():
    """Create convenient launch scripts for Mac"""
    print("Creating Mac launch scripts...")
    
    # Create a simple run script
    run_script = """#!/bin/bash
# Email Guardian Mac Runner
echo "=== Starting Email Guardian on Mac ==="

# Export environment variables
export FLASK_ENV=development
export FLASK_DEBUG=true
export SESSION_SECRET=local-dev-secret-key-change-in-production-mac
export DATABASE_URL=sqlite:///instance/email_guardian.db
export FAST_MODE=true

echo "✓ Environment configured"
echo "✓ Starting server on http://localhost:5000"
echo "✓ Press Ctrl+C to stop"
echo ""

python3 run_local.py
"""
    
    with open("run_mac.sh", "w") as f:
        f.write(run_script)
    
    os.chmod("run_mac.sh", 0o755)
    print("✓ Mac launch script created (run_mac.sh)")

def main():
    """Main setup function for Mac"""
    print("=== Email Guardian Mac Setup ===")
    print()
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("✗ Python 3.8 or higher is required")
        print("Install Python 3.8+ using Homebrew: brew install python3")
        sys.exit(1)
    
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor} detected")
    
    # Check and install Homebrew if needed
    if not check_homebrew():
        sys.exit(1)
    
    # Run setup steps
    install_system_dependencies()
    install_python_dependencies()
    create_directories()
    setup_database()
    create_env_file()
    create_launch_scripts()
    setup_basic_config()
    
    print()
    print("=== Mac Setup Complete! ===")
    print()
    print("To run the application:")
    print("1. Run: ./run_mac.sh")
    print("   OR")
    print("2. Run: python3 run_local.py")
    print("3. Open your browser to http://localhost:5000")
    print()
    print("Mac-specific files created:")
    print("  - .env.mac (environment configuration)")
    print("  - run_mac.sh (launch script)")
    print()
    print("The application is configured to use SQLite database locally.")

if __name__ == "__main__":
    main()