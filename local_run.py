
#!/usr/bin/env python3
"""
Local development runner for Email Guardian
Entry point for local development with SQLite database
"""

import os
import sys
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

def load_env_file():
    """Load environment variables from .env file if it exists"""
    env_file = Path(".env")
    if env_file.exists():
        print("Loading environment variables from .env file...")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

def setup_local_environment():
    """Set up local development environment variables"""
    
    # Load .env file if it exists
    load_env_file()
    
    # Set default local development environment variables
    os.environ.setdefault('FLASK_ENV', 'development')
    os.environ.setdefault('FLASK_DEBUG', 'true')
    os.environ.setdefault('SESSION_SECRET', 'local-dev-secret-key')
    os.environ.setdefault('DATABASE_URL', 'sqlite:///instance/email_guardian.db')
    os.environ.setdefault('FAST_MODE', 'true')
    os.environ.setdefault('CHUNK_SIZE', '1000')
    os.environ.setdefault('MAX_ML_RECORDS', '5000')
    
    # Ensure directories exist
    directories = ['uploads', 'data', 'instance']
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)

def main():
    """Main local development runner"""
    print("=== Email Guardian Local Development Server ===")
    
    # Setup environment
    setup_local_environment()
    
    # Import and run the app
    try:
        from app import app
        print("Starting local development server...")
        print("Database: SQLite (instance/email_guardian.db)")
        print("Access the application at: http://localhost:5000")
        print("Press Ctrl+C to stop the server")
        print()
        
        # Run the Flask development server
        app.run(
            debug=True,
            host='127.0.0.1',
            port=5000,
            use_reloader=True
        )
        
    except ImportError as e:
        print(f"✗ Failed to import application: {e}")
        print("Make sure you've run the setup script: python local_setup.py")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Failed to start application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
