
#!/usr/bin/env python3
"""
Simple local runner for Email Guardian
Quick start script for local development
"""

import os
import sys
from pathlib import Path

def main():
    """Run the Email Guardian application locally"""
    
    # Set up local environment
    os.environ['FLASK_ENV'] = 'development'
    os.environ['FLASK_DEBUG'] = 'true'
    os.environ['SESSION_SECRET'] = 'local-dev-secret'
    os.environ['DATABASE_URL'] = 'sqlite:///instance/email_guardian.db'
    os.environ['FAST_MODE'] = 'true'
    
    # Ensure directories exist
    Path('uploads').mkdir(exist_ok=True)
    Path('data').mkdir(exist_ok=True)
    Path('instance').mkdir(exist_ok=True)
    
    print("Starting Email Guardian locally...")
    print("Database: SQLite (local)")
    print("URL: http://localhost:5000")
    print()
    
    # Import and run the app
    try:
        from app import app
        app.run(debug=True, host='127.0.0.1', port=5000)
    except Exception as e:
        print(f"Error starting application: {e}")
        print("Try running: python local_setup.py first")

if __name__ == "__main__":
    main()
