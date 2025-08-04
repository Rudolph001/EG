
#!/usr/bin/env python3
"""
Simple local runner for Email Guardian
Quick start script for local development
"""

import os
import sys
import sqlite3
from pathlib import Path

def setup_database():
    """Initialize the SQLite database"""
    db_path = Path("instance/email_guardian.db")
    
    # Create the database file if it doesn't exist
    if not db_path.exists():
        print("Creating SQLite database...")
        try:
            # Create a connection to initialize the database file
            conn = sqlite3.connect(str(db_path))
            conn.close()
            print("✓ Database file created")
        except Exception as e:
            print(f"✗ Failed to create database: {e}")
            return False
    return True

def main():
    """Run the Email Guardian application locally"""
    
    print("=== Email Guardian Local Startup ===")
    
    # Set up local environment
    os.environ['FLASK_ENV'] = 'development'
    os.environ['FLASK_DEBUG'] = 'true'
    os.environ['SESSION_SECRET'] = 'local-dev-secret'
    os.environ['DATABASE_URL'] = 'sqlite:///instance/email_guardian.db'
    os.environ['FAST_MODE'] = 'true'
    
    # Ensure directories exist with proper permissions
    directories = ['uploads', 'data', 'instance', 'static/css', 'static/js', 'templates']
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    print("✓ Directories created")
    
    # Setup database
    if not setup_database():
        sys.exit(1)
    
    print("Starting Email Guardian locally...")
    print("Database: SQLite (instance/email_guardian.db)")
    print("URL: http://0.0.0.0:5000")
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
        app.run(debug=True, host='0.0.0.0', port=5000)
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        print("Try running: python local_setup.py first")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error starting application: {e}")
        print("Try running: python local_setup.py first")
        sys.exit(1)

if __name__ == "__main__":
    main()
