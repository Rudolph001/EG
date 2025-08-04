
#!/usr/bin/env python3
"""
Mac-specific local runner for Email Guardian
Handles macOS permissions and SQLite setup
"""

import os
import sys
import sqlite3
import stat
from pathlib import Path

def setup_local_environment():
    """Set up local development environment for Mac"""
    print("=== Email Guardian Mac Local Setup ===")
    
    # Set environment variables for local development
    os.environ['FLASK_ENV'] = 'development'
    os.environ['FLASK_DEBUG'] = 'true'
    os.environ['SESSION_SECRET'] = 'local-dev-secret-key'
    
    # Use current directory for database (better permissions on Mac)
    db_path = os.path.join(os.getcwd(), "email_guardian_local.db")
    os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'
    
    print(f"Database will be created at: {db_path}")
    
    # Create necessary directories
    directories = ['uploads', 'data', 'static/css', 'static/js', 'templates']
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        # Set proper permissions on Mac
        os.chmod(directory, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    
    # Test SQLite database creation
    try:
        # Remove existing database if it has permission issues
        if os.path.exists(db_path):
            try:
                # Test if we can write to it
                conn = sqlite3.connect(db_path)
                conn.execute("CREATE TABLE IF NOT EXISTS permission_test (id INTEGER)")
                conn.commit()
                conn.close()
                print("✓ Existing database is accessible")
            except Exception:
                print("Removing inaccessible database file...")
                os.remove(db_path)
        
        # Create new database
        if not os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE IF NOT EXISTS setup_test (id INTEGER PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            conn.commit()
            conn.close()
            
            # Set proper file permissions
            os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
            print("✓ Database created successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ Database setup failed: {e}")
        # Set to use in-memory database as fallback
        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        print("Using in-memory database as fallback")
        return True

def main():
    """Main function to run the app"""
    try:
        # Setup environment
        if not setup_local_environment():
            sys.exit(1)
        
        # Import and run the app
        from app import app
        
        print("\n=== Starting Email Guardian ===")
        print("Access the application at: http://localhost:5000")
        print("Press Ctrl+C to stop the server")
        print()
        
        # Run the Flask development server
        app.run(
            debug=True,
            host='0.0.0.0',
            port=5000,
            use_reloader=False  # Disable reloader to avoid permission issues
        )
        
    except KeyboardInterrupt:
        print("\n\nServer stopped by user")
    except Exception as e:
        print(f"✗ Failed to start application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
