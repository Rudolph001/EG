
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
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        # Set proper permissions for Mac/Linux
        if hasattr(os, 'chmod'):
            os.chmod(str(dir_path), 0o755)
    
    print("✓ Directories created with proper permissions")

def setup_database():
    """Initialize SQLite database"""
    print("Setting up SQLite database...")
    db_path = "instance/email_guardian.db"
    
    # Create instance directory if it doesn't exist
    instance_dir = Path("instance")
    instance_dir.mkdir(exist_ok=True)
    
    # Set proper permissions for the instance directory
    if hasattr(os, 'chmod'):
        os.chmod(str(instance_dir), 0o755)
    
    # Create and initialize database file properly
    if not os.path.exists(db_path):
        try:
            # Create database file with proper initialization
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE IF NOT EXISTS test_table (id INTEGER)")
            conn.commit()
            conn.close()
            
            # Set proper file permissions
            if hasattr(os, 'chmod'):
                os.chmod(db_path, 0o664)
            
            print("✓ Database file created and initialized")
        except Exception as e:
            print(f"✗ Failed to create database: {e}")
            # Try alternative approach
            try:
                Path(db_path).touch()
                if hasattr(os, 'chmod'):
                    os.chmod(db_path, 0o664)
                print("✓ Database file created (alternative method)")
            except Exception as e2:
                print(f"✗ Failed to create database file: {e2}")
                return False
    
    # Test database access
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT 1")
        conn.close()
        print("✓ Database access verified")
    except Exception as e:
        print(f"✗ Database access test failed: {e}")
        return False
    
    print("✓ Database setup complete")
    return True

def create_env_file():
    """Create a local .env file"""
    print("Creating local environment file...")
    
    env_content = """# Email Guardian Local Configuration - TURBO MODE
FLASK_ENV=development
FLASK_DEBUG=true
SESSION_SECRET=local-dev-secret-key-change-in-production
DATABASE_URL=sqlite:///instance/email_guardian.db
FAST_MODE=true

# TURBO MODE - Optimized for fast local processing
EMAIL_GUARDIAN_CHUNK_SIZE=2000
EMAIL_GUARDIAN_MAX_ML_RECORDS=100000
EMAIL_GUARDIAN_ML_ESTIMATORS=10
EMAIL_GUARDIAN_BATCH_SIZE=500
EMAIL_GUARDIAN_PROGRESS_INTERVAL=500
EMAIL_GUARDIAN_SKIP_ADVANCED=true
EMAIL_GUARDIAN_TFIDF_FEATURES=200
EMAIL_GUARDIAN_ML_CHUNK_SIZE=5000

# Legacy settings for compatibility
CHUNK_SIZE=2000
MAX_ML_RECORDS=100000
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
    if not setup_database():
        print("✗ Database setup failed. Please check permissions and try again.")
        sys.exit(1)
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
