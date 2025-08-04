#!/usr/bin/env python3
"""
Mac-specific local runner for Email Guardian
Optimized for macOS environment and paths
"""

import os
import sys
import sqlite3
from pathlib import Path

def setup_database():
    """Initialize the SQLite database for Mac"""
    db_path = Path("instance/email_guardian.db")
    
    # Create the database file if it doesn't exist
    if not db_path.exists():
        print("Creating SQLite database...")
        try:
            # Ensure instance directory exists with proper permissions
            instance_dir = db_path.parent
            instance_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(str(instance_dir), 0o755)
            
            # Create a connection to initialize the database file
            conn = sqlite3.connect(str(db_path))
            conn.close()
            
            # Set Mac-friendly permissions
            os.chmod(str(db_path), 0o664)
            print("✓ Database file created")
        except Exception as e:
            print(f"✗ Failed to create database: {e}")
            return False
    return True

def check_mac_environment():
    """Check Mac-specific environment setup"""
    print("Checking Mac environment...")
    
    # Check if we're running on macOS
    if sys.platform != 'darwin':
        print("⚠ Warning: This script is optimized for macOS")
    else:
        print("✓ Running on macOS")
    
    # Check for required directories
    required_dirs = ['uploads', 'data', 'instance', 'static', 'templates']
    for directory in required_dirs:
        if not Path(directory).exists():
            print(f"⚠ Creating missing directory: {directory}")
            Path(directory).mkdir(parents=True, exist_ok=True)
            os.chmod(str(Path(directory)), 0o755)
    
    print("✓ Directory structure verified")

def main():
    """Run the Email Guardian application on Mac"""
    
    print("=== Email Guardian Mac Startup ===")
    
    # Check Mac environment
    check_mac_environment()
    
    # Set up local environment with Mac-specific settings
    os.environ['FLASK_ENV'] = 'development'
    os.environ['FLASK_DEBUG'] = 'true'
    os.environ['SESSION_SECRET'] = 'local-dev-secret-mac'
    os.environ['DATABASE_URL'] = 'sqlite:///instance/email_guardian.db'
    os.environ['FAST_MODE'] = 'true'
    
    # Mac-specific Python path setup
    current_dir = os.getcwd()
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    print("✓ Mac environment configured")
    
    # Setup database
    if not setup_database():
        sys.exit(1)
    
    print("Starting Email Guardian on Mac...")
    print("Database: SQLite (instance/email_guardian.db)")
    print("URL: http://localhost:5000")
    print("Environment: macOS Development")
    print()
    
    # Import and run the app
    try:
        from app import app
        
        # Ensure database tables are created
        with app.app_context():
            from models import db
            db.create_all()
            print("✓ Database tables initialized")
        
        print("Server starting... Press Ctrl+C to stop")
        print("Note: On Mac, the server may take a moment to start")
        
        # Run with Mac-optimized settings
        app.run(
            debug=True, 
            host='localhost',  # Use localhost for Mac security
            port=5000,
            threaded=True,     # Better for Mac performance
            use_reloader=True
        )
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        print("Try running: python3 setup_mac.py first")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error starting application: {e}")
        print("Try running: python3 setup_mac.py first")
        sys.exit(1)

if __name__ == "__main__":
    main()