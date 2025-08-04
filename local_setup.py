
#!/usr/bin/env python3
"""
Local setup script for Email Guardian
Run this script to set up the application for local development
"""

import os
import sys
import subprocess
import sqlite3
from pathlib import Path

def install_dependencies():
    """Install Python dependencies"""
    print("Installing Python dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✓ Dependencies installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install dependencies: {e}")
        sys.exit(1)

def create_directories():
    """Create necessary directories"""
    print("Creating necessary directories...")
    directories = ['uploads', 'data', 'instance', 'static/css', 'static/js', 'templates']
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    print("✓ Directories created")

def setup_database():
    """Initialize SQLite database"""
    print("Setting up SQLite database...")
    db_path = "instance/email_guardian.db"
    
    # Create instance directory if it doesn't exist
    Path("instance").mkdir(exist_ok=True)
    
    # Create empty database file if it doesn't exist
    if not os.path.exists(db_path):
        Path(db_path).touch()
    
    print("✓ Database setup complete")

def create_env_file():
    """Create a local .env file"""
    print("Creating local environment file...")
    
    env_content = """# Email Guardian Local Configuration
FLASK_ENV=development
FLASK_DEBUG=true
SESSION_SECRET=local-dev-secret-key-change-in-production
DATABASE_URL=sqlite:///instance/email_guardian.db
FAST_MODE=true
CHUNK_SIZE=1000
MAX_ML_RECORDS=5000
"""
    
    # Create .env file for local development
    with open(".env", "w") as f:
        f.write(env_content)
    
    print("✓ Local environment file created (.env)")

def setup_basic_config():
    """Run basic configuration setup"""
    print("Setting up basic configuration...")
    try:
        subprocess.check_call([sys.executable, "setup_basic_config.py"])
        print("✓ Basic configuration setup complete")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to setup basic configuration: {e}")
        print("You can run 'python setup_basic_config.py' manually later")

def main():
    """Main setup function"""
    print("=== Email Guardian Local Setup ===")
    print()
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("✗ Python 3.8 or higher is required")
        sys.exit(1)
    
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor} detected")
    
    # Run setup steps
    install_dependencies()
    create_directories()
    setup_database()
    create_env_file()
    setup_basic_config()
    
    print()
    print("=== Setup Complete! ===")
    print()
    print("To run the application:")
    print("1. Run: python local_run.py")
    print("2. Open your browser to http://localhost:5000")
    print()
    print("The application is configured to use SQLite database locally.")

if __name__ == "__main__":
    main()
