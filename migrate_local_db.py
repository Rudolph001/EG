#!/usr/bin/env python3
"""
Database migration script for local SQLite database
Adds missing flagging columns to email_records table
"""

import sqlite3
import os
import sys
from pathlib import Path

def add_flagging_columns_to_sqlite(db_path):
    """Add flagging columns to SQLite database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if flagging columns already exist
        cursor.execute("PRAGMA table_info(email_records)")
        columns = [column[1] for column in cursor.fetchall()]
        
        flagging_columns = [
            'is_flagged',
            'flag_reason', 
            'flagged_at',
            'flagged_by',
            'previously_flagged'
        ]
        
        columns_to_add = []
        for col in flagging_columns:
            if col not in columns:
                columns_to_add.append(col)
        
        if not columns_to_add:
            print("✓ All flagging columns already exist in database")
            conn.close()
            return True
            
        print(f"Adding {len(columns_to_add)} missing flagging columns...")
        
        # Add missing flagging columns
        for column in columns_to_add:
            if column == 'is_flagged':
                cursor.execute(f"ALTER TABLE email_records ADD COLUMN {column} BOOLEAN DEFAULT 0")
            elif column == 'previously_flagged':
                cursor.execute(f"ALTER TABLE email_records ADD COLUMN {column} BOOLEAN DEFAULT 0")
            elif column in ['flagged_at']:
                cursor.execute(f"ALTER TABLE email_records ADD COLUMN {column} TIMESTAMP")
            else:  # flag_reason, flagged_by
                cursor.execute(f"ALTER TABLE email_records ADD COLUMN {column} TEXT")
            print(f"✓ Added column: {column}")
        
        conn.commit()
        conn.close()
        
        print(f"✓ Successfully added {len(columns_to_add)} flagging columns to SQLite database")
        return True
        
    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False

def migrate_local_database():
    """Main migration function for local development"""
    print("=== Email Guardian Local Database Migration ===")
    
    # Check for common SQLite database locations
    possible_paths = [
        "instance/email_guardian.db",
        "email_guardian_local.db",
        "email_guardian.db"
    ]
    
    db_path = None
    for path in possible_paths:
        if os.path.exists(path):
            db_path = path
            break
    
    if not db_path:
        print("No existing SQLite database found. Database will be created with correct schema when app starts.")
        return True
    
    print(f"Found SQLite database: {db_path}")
    
    # Backup database before migration
    backup_path = f"{db_path}.backup"
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"✓ Database backed up to: {backup_path}")
    except Exception as e:
        print(f"Warning: Could not create backup: {e}")
    
    # Perform migration
    success = add_flagging_columns_to_sqlite(db_path)
    
    if success:
        print("✓ Database migration completed successfully!")
        print("Your local database now has the latest schema.")
    else:
        print("✗ Database migration failed!")
        if os.path.exists(backup_path):
            print(f"Backup is available at: {backup_path}")
    
    return success

if __name__ == "__main__":
    migrate_local_database()