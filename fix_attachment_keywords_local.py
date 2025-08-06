#!/usr/bin/env python3
"""
Fix local SQLite database - Add missing added_by column to attachment_keywords table
This resolves the schema synchronization issue between PostgreSQL (Replit) and SQLite (local)
"""

import sqlite3
import os
from datetime import datetime

def fix_attachment_keywords_table():
    """Add missing added_by column to attachment_keywords table"""
    db_path = os.path.join('instance', 'email_guardian.db')
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found at {db_path}")
        print("   Please ensure you're running this from the project root directory")
        return False
    
    print(f"🔧 Fixing attachment_keywords table in {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if added_by column already exists
        cursor.execute("PRAGMA table_info(attachment_keywords)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'added_by' in columns:
            print("✅ Column 'added_by' already exists in attachment_keywords table")
            conn.close()
            return True
        
        # Add the missing column
        print("➕ Adding 'added_by' column to attachment_keywords table...")
        cursor.execute("""
            ALTER TABLE attachment_keywords 
            ADD COLUMN added_by TEXT
        """)
        
        # Update existing records to have a default value
        cursor.execute("""
            UPDATE attachment_keywords 
            SET added_by = 'system' 
            WHERE added_by IS NULL
        """)
        
        conn.commit()
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(attachment_keywords)")
        updated_columns = [column[1] for column in cursor.fetchall()]
        
        if 'added_by' in updated_columns:
            print("✅ Successfully added 'added_by' column to attachment_keywords table")
            print(f"📊 Updated {cursor.rowcount} existing records with default 'system' value")
        else:
            print("❌ Failed to add 'added_by' column")
            return False
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error fixing attachment_keywords table: {e}")
        return False

def verify_fix():
    """Verify the fix worked by testing a simple query"""
    db_path = os.path.join('instance', 'email_guardian.db')
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Test the query that was failing
        cursor.execute("SELECT COUNT(*) FROM attachment_keywords WHERE is_active = 1")
        count = cursor.fetchone()[0]
        
        print(f"✅ Verification successful: Found {count} active attachment keywords")
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Email Guardian - Local Database Schema Fix")
    print("=" * 50)
    
    success = fix_attachment_keywords_table()
    
    if success:
        print("\n🔍 Verifying fix...")
        if verify_fix():
            print("\n✅ LOCAL DATABASE SCHEMA FIX COMPLETED SUCCESSFULLY!")
            print("   Your admin dashboard should now work properly.")
        else:
            print("\n❌ Fix applied but verification failed. Please check the database manually.")
    else:
        print("\n❌ SCHEMA FIX FAILED!")
        print("   Please check the error messages above and try again.")
    
    print("\nNext steps:")
    print("1. Run this script: python fix_attachment_keywords_local.py")
    print("2. Start your local app: python local_run.py")
    print("3. Test the admin dashboard")