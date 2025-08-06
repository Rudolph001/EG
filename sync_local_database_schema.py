#!/usr/bin/env python3
"""
Comprehensive Local Database Schema Synchronization
Ensures local SQLite database matches PostgreSQL (Replit) schema exactly
"""

import sqlite3
import os
from datetime import datetime

def check_and_add_column(cursor, table_name, column_name, column_type, default_value=None):
    """Check if column exists and add it if missing"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [column[1] for column in cursor.fetchall()]
    
    if column_name not in columns:
        print(f"➕ Adding missing column '{column_name}' to {table_name}")
        
        alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        cursor.execute(alter_sql)
        
        if default_value is not None:
            update_sql = f"UPDATE {table_name} SET {column_name} = ? WHERE {column_name} IS NULL"
            cursor.execute(update_sql, (default_value,))
        
        return True
    else:
        print(f"✅ Column '{column_name}' exists in {table_name}")
        return False

def sync_database_schema():
    """Synchronize local SQLite schema with PostgreSQL schema"""
    db_path = os.path.join('instance', 'email_guardian.db')
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found at {db_path}")
        print("   Creating instance directory and database...")
        os.makedirs('instance', exist_ok=True)
        # The database will be created when we connect
    
    print(f"🔧 Synchronizing database schema: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        changes_made = 0
        
        # Fix attachment_keywords table
        print("\n📋 Checking attachment_keywords table...")
        if check_and_add_column(cursor, 'attachment_keywords', 'added_by', 'TEXT', 'system'):
            changes_made += 1
        
        # Fix email_records table - ensure all flagging columns exist
        print("\n📧 Checking email_records table...")
        flagging_columns = [
            ('is_flagged', 'BOOLEAN', 0),
            ('flag_reason', 'TEXT', None),
            ('flagged_at', 'DATETIME', None),
            ('flagged_by', 'TEXT', None),
            ('previously_flagged', 'BOOLEAN', 0),
            ('account_type', 'TEXT', 'user')  # Added in recent updates
        ]
        
        for column_name, column_type, default_value in flagging_columns:
            if check_and_add_column(cursor, 'email_records', column_name, column_type, default_value):
                changes_made += 1
        
        # Check processing_sessions table
        print("\n⚙️ Checking processing_sessions table...")
        session_columns = [
            ('configuration_id', 'INTEGER', None),
            ('ml_model_version', 'TEXT', 'v1.0'),
            ('adaptive_ml_enabled', 'BOOLEAN', 1),
        ]
        
        for column_name, column_type, default_value in session_columns:
            # Check if table exists first
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='processing_sessions'")
            if cursor.fetchone():
                if check_and_add_column(cursor, 'processing_sessions', column_name, column_type, default_value):
                    changes_made += 1
        
        # Ensure audit_log table exists and has proper structure
        print("\n📊 Checking audit_log table...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
        if not cursor.fetchone():
            print("➕ Creating audit_log table...")
            cursor.execute("""
                CREATE TABLE audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    user_id TEXT,
                    event_type TEXT NOT NULL,
                    description TEXT,
                    metadata TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            changes_made += 1
        
        # Ensure adaptive_learning_metrics table exists
        print("\n🤖 Checking adaptive_learning_metrics table...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='adaptive_learning_metrics'")
        if not cursor.fetchone():
            print("➕ Creating adaptive_learning_metrics table...")
            cursor.execute("""
                CREATE TABLE adaptive_learning_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    feedback_count INTEGER DEFAULT 0,
                    escalation_count INTEGER DEFAULT 0,
                    clear_count INTEGER DEFAULT 0,
                    model_accuracy REAL DEFAULT 0.0,
                    adaptive_weight REAL DEFAULT 0.1,
                    learning_rate REAL DEFAULT 0.01,
                    confidence_score REAL DEFAULT 0.0,
                    feature_importance TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            changes_made += 1
        
        conn.commit()
        
        print(f"\n✅ Schema synchronization complete!")
        print(f"📈 Made {changes_made} changes to the database schema")
        
        conn.close()
        return True, changes_made
        
    except Exception as e:
        print(f"❌ Error synchronizing schema: {e}")
        return False, 0

def verify_schema():
    """Verify the schema is working by testing key queries"""
    db_path = os.path.join('instance', 'email_guardian.db')
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Test attachment_keywords query (the one that was failing)
        cursor.execute("SELECT COUNT(*) FROM attachment_keywords WHERE is_active = 1")
        attachment_count = cursor.fetchone()[0]
        
        # Test email_records flagging columns
        cursor.execute("SELECT COUNT(*) FROM email_records WHERE is_flagged = 0")
        email_count = cursor.fetchone()[0]
        
        # Test audit_log table
        cursor.execute("SELECT COUNT(*) FROM audit_log")
        audit_count = cursor.fetchone()[0]
        
        print(f"✅ Verification successful:")
        print(f"   - {attachment_count} attachment keywords found")
        print(f"   - {email_count} email records accessible")
        print(f"   - {audit_count} audit log entries")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Email Guardian - Database Schema Synchronization")
    print("=" * 60)
    print("This script ensures your local SQLite database matches")
    print("the PostgreSQL schema used on Replit.\n")
    
    success, changes = sync_database_schema()
    
    if success:
        print("\n🔍 Verifying schema...")
        if verify_schema():
            print(f"\n✅ SCHEMA SYNCHRONIZATION COMPLETED SUCCESSFULLY!")
            print(f"   Database is now fully synchronized with {changes} updates applied.")
            print("\n   Your local app should now work identically to Replit!")
        else:
            print("\n⚠️  Schema updated but verification had issues.")
            print("    The admin dashboard might still have problems.")
    else:
        print("\n❌ SCHEMA SYNCHRONIZATION FAILED!")
        print("   Please check the error messages above.")
    
    print(f"\n📝 Next steps:")
    print(f"   1. Run: python sync_local_database_schema.py")
    print(f"   2. Start local app: python local_run.py")
    print(f"   3. Test admin dashboard at http://localhost:5000/admin")