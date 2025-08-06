
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
    
    # Use absolute path for SQLite database
    db_file_path = os.path.abspath("instance/email_guardian.db")
    os.environ.setdefault('DATABASE_URL', f'sqlite:///{db_file_path}')
    
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
    
    # Verify database file can be created
    db_path = Path("instance/email_guardian.db")
    try:
        # Ensure parent directory exists with proper permissions
        db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        
        # Set proper permissions for the instance directory
        os.chmod(str(db_path.parent), 0o755)
        
        # Test database connection
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute("SELECT 1")  # Test write access
        conn.close()
        print("✓ Database connection test successful")
        print(f"✓ Database file accessible: {db_path}")
        
        # Setup and migrate database schema
        try:
            from setup_local_database import setup_local_database
            print("Setting up local database schema...")
            setup_local_database()
        except Exception as migrate_error:
            print(f"Note: Database setup failed: {migrate_error}")
            # Fallback to basic migration
            try:
                from migrate_local_db import add_flagging_columns_to_sqlite
                print("Trying basic migration...")
                add_flagging_columns_to_sqlite(str(db_path))
            except Exception as e2:
                print(f"Note: Migration fallback failed: {e2}")
            
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        print("Creating database file...")
        try:
            # Force create the database file
            if db_path.exists():
                db_path.unlink()  # Remove corrupted file
            
            # Create database with proper permissions
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE IF NOT EXISTS test_table (id INTEGER)")
            conn.commit()
            conn.close()
            
            # Set proper file permissions
            os.chmod(str(db_path), 0o644)
            
            print("✓ Database file created successfully")
        except Exception as create_error:
            print(f"✗ Failed to create database file: {create_error}")
            
            # Try alternative database location
            alt_db_path = Path("email_guardian_temp.db")
            try:
                print("Trying alternative database location...")
                conn = sqlite3.connect(str(alt_db_path))
                conn.execute("CREATE TABLE IF NOT EXISTS test_table (id INTEGER)")
                conn.commit()
                conn.close()
                
                # Update environment variable to use alternative path
                os.environ['DATABASE_URL'] = f'sqlite:///{alt_db_path.absolute()}'
                print(f"✓ Alternative database created: {alt_db_path}")
            except Exception as alt_error:
                print(f"✗ Failed to create alternative database: {alt_error}")
                sys.exit(1)
    
    # Import and run the app
    try:
        from app import app
        
        # Initialize database tables
        with app.app_context():
            from models import db
            db.create_all()
            print("✓ Database tables created/verified")
        
        print("Starting local development server...")
        print("Database: SQLite (instance/email_guardian.db)")
        print("Access the application at: http://0.0.0.0:5000")
        print("Press Ctrl+C to stop the server")
        print()
        
        # Run the Flask development server
        app.run(
            debug=True,
            host='0.0.0.0',
            port=5000,
            use_reloader=True
        )
        
    except ImportError as e:
        print(f"✗ Failed to import application: {e}")
        print("Make sure you've run the setup script: python local_setup.py")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Failed to start application: {e}")
        print(f"Error details: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
