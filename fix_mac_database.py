#!/usr/bin/env python3
"""
Simple fix for Mac SQLite database issues
Run this to create a working database with proper permissions
"""

import os
import sqlite3
import sys
from pathlib import Path

def fix_mac_database():
    """Fix SQLite database permissions on Mac"""
    print("=== Fixing Mac Database Issues ===")
    
    # Remove any existing problematic files
    instance_dir = Path("instance")
    db_path = instance_dir / "email_guardian.db"
    
    # Clean up
    if db_path.exists():
        print("Removing existing database file...")
        try:
            os.remove(str(db_path))
        except Exception as e:
            print(f"Could not remove existing file: {e}")
    
    # Ensure instance directory exists with full permissions
    print("Creating instance directory...")
    instance_dir.mkdir(exist_ok=True)
    os.chmod(str(instance_dir), 0o777)  # Full permissions for Mac
    
    # Create database in current directory instead
    print("Creating database file with proper permissions...")
    try:
        # Create in current directory first (we know this works)
        temp_db = Path("email_guardian_temp.db")
        conn = sqlite3.connect(str(temp_db))
        
        # Create a basic table to initialize the database
        conn.execute("""
            CREATE TABLE IF NOT EXISTS test_init (
                id INTEGER PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("INSERT INTO test_init (id) VALUES (1)")
        conn.commit()
        conn.close()
        
        # Set full permissions
        os.chmod(str(temp_db), 0o666)
        
        # Move to instance directory
        final_path = instance_dir / "email_guardian.db"
        os.rename(str(temp_db), str(final_path))
        os.chmod(str(final_path), 0o666)
        
        print(f"✓ Database created successfully: {final_path}")
        
        # Test the database
        conn = sqlite3.connect(str(final_path))
        result = conn.execute("SELECT COUNT(*) FROM test_init").fetchone()
        conn.close()
        print(f"✓ Database test successful: {result[0]} test record found")
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to create database: {e}")
        
        # Alternative: Use temp directory
        print("Trying alternative location...")
        try:
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / "email_guardian"
            temp_dir.mkdir(exist_ok=True)
            alt_db = temp_dir / "email_guardian.db"
            
            conn = sqlite3.connect(str(alt_db))
            conn.execute("CREATE TABLE IF NOT EXISTS test_init (id INTEGER)")
            conn.execute("INSERT INTO test_init (id) VALUES (1)")
            conn.commit()
            conn.close()
            
            print(f"✓ Alternative database created: {alt_db}")
            print(f"Update your .env file to use: DATABASE_URL=sqlite:///{alt_db}")
            return True
            
        except Exception as e2:
            print(f"✗ Alternative method also failed: {e2}")
            return False

def update_env_for_mac():
    """Update .env file with Mac-friendly settings"""
    print("Updating environment configuration for Mac...")
    
    # Check if database was created successfully
    db_path = Path("instance/email_guardian.db")
    if not db_path.exists():
        # Use temp directory
        import tempfile
        temp_dir = Path(tempfile.gettempdir()) / "email_guardian"
        db_path = temp_dir / "email_guardian.db"
    
    env_content = f"""# Email Guardian Mac Configuration
FLASK_ENV=development
FLASK_DEBUG=true
SESSION_SECRET=local-dev-secret-key-mac
DATABASE_URL=sqlite:///{db_path.absolute()}
FAST_MODE=true

# TURBO MODE for Mac
EMAIL_GUARDIAN_CHUNK_SIZE=2000
EMAIL_GUARDIAN_MAX_ML_RECORDS=100000
EMAIL_GUARDIAN_ML_ESTIMATORS=5
EMAIL_GUARDIAN_BATCH_SIZE=1000
EMAIL_GUARDIAN_PROGRESS_INTERVAL=1000
EMAIL_GUARDIAN_SKIP_ADVANCED=true
EMAIL_GUARDIAN_TFIDF_FEATURES=100
EMAIL_GUARDIAN_ML_CHUNK_SIZE=10000

# Legacy compatibility
CHUNK_SIZE=2000
MAX_ML_RECORDS=100000
"""
    
    with open(".env", "w") as f:
        f.write(env_content)
    
    print("✓ Environment file updated (.env)")
    print(f"✓ Database path: {db_path.absolute()}")

def main():
    """Main function"""
    if not fix_mac_database():
        print("\n✗ Could not create database. Please check your permissions.")
        print("Try running: sudo python3 fix_mac_database.py")
        return False
    
    update_env_for_mac()
    
    print("\n=== Mac Database Fix Complete! ===")
    print("Now run: python3 run_local.py")
    print("Or run: python3 local_run.py")
    
    return True

if __name__ == "__main__":
    if not main():
        sys.exit(1)