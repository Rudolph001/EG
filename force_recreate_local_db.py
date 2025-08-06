#!/usr/bin/env python3
"""
Force recreate local SQLite database with correct schema
This will delete existing database and create a new one with complete schema
"""

import os
import sys
import sqlite3
from pathlib import Path

def force_recreate_database():
    """Force recreation of local database with complete schema"""
    print("=== Force Recreating Local Database ===")
    
    # Database paths to check and remove
    db_paths = [
        "instance/email_guardian.db",
        "instance/email_guardian.db.backup",
        "email_guardian_local.db",
        "email_guardian.db"
    ]
    
    # Remove all existing database files
    removed_files = []
    for db_path in db_paths:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
                removed_files.append(db_path)
                print(f"✓ Removed old database: {db_path}")
            except Exception as e:
                print(f"Warning: Could not remove {db_path}: {e}")
    
    if removed_files:
        print(f"Removed {len(removed_files)} old database files")
    else:
        print("No existing database files found")
    
    # Create instance directory
    Path("instance").mkdir(exist_ok=True, mode=0o755)
    
    # Create new database with complete schema
    db_path = "instance/email_guardian.db"
    print(f"Creating new database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        create_complete_schema(cursor)
        
        conn.commit()
        conn.close()
        
        # Set proper permissions
        os.chmod(db_path, 0o664)
        
        print("✓ Database created successfully with complete schema")
        print(f"✓ Database location: {os.path.abspath(db_path)}")
        
        # Verify schema
        verify_schema(db_path)
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to create database: {e}")
        return False

def create_complete_schema(cursor):
    """Create complete database schema"""
    
    print("Creating database tables...")
    
    # Processing Sessions
    cursor.execute("""
        CREATE TABLE processing_sessions (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_records INTEGER DEFAULT 0,
            processed_records INTEGER DEFAULT 0,
            status TEXT DEFAULT 'uploaded',
            error_message TEXT,
            processing_stats TEXT,
            data_path TEXT,
            is_compressed BOOLEAN DEFAULT 0,
            current_stage INTEGER DEFAULT 0,
            stage_progress REAL DEFAULT 0.0,
            workflow_stages TEXT,
            exclusion_applied BOOLEAN DEFAULT 0,
            whitelist_applied BOOLEAN DEFAULT 0,
            rules_applied BOOLEAN DEFAULT 0,
            ml_applied BOOLEAN DEFAULT 0,
            current_chunk INTEGER DEFAULT 0,
            total_chunks INTEGER DEFAULT 0
        )
    """)
    
    # Email Records with ALL columns including flagging
    cursor.execute("""
        CREATE TABLE email_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            record_id TEXT NOT NULL,
            time TEXT,
            sender TEXT,
            subject TEXT,
            attachments TEXT,
            recipients TEXT,
            recipients_email_domain TEXT,
            leaver TEXT,
            termination_date TEXT,
            wordlist_attachment TEXT,
            wordlist_subject TEXT,
            bunit TEXT,
            department TEXT,
            status TEXT,
            user_response TEXT,
            final_outcome TEXT,
            justification TEXT,
            policy_name TEXT,
            excluded_by_rule TEXT,
            whitelisted BOOLEAN DEFAULT 0,
            rule_matches TEXT,
            ml_risk_score REAL,
            ml_anomaly_score REAL,
            risk_level TEXT,
            ml_explanation TEXT,
            case_status TEXT DEFAULT 'Active',
            assigned_to TEXT,
            notes TEXT,
            escalated_at TIMESTAMP,
            resolved_at TIMESTAMP,
            is_flagged BOOLEAN DEFAULT 0,
            flag_reason TEXT,
            flagged_at TIMESTAMP,
            flagged_by TEXT,
            previously_flagged BOOLEAN DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES processing_sessions (id)
        )
    """)
    
    # Rules
    cursor.execute("""
        CREATE TABLE rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            rule_type TEXT NOT NULL,
            conditions TEXT,
            actions TEXT,
            priority INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Whitelist Domains
    cursor.execute("""
        CREATE TABLE whitelist_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE NOT NULL,
            domain_type TEXT,
            added_by TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    
    # Attachment Keywords
    cursor.execute("""
        CREATE TABLE attachment_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            keyword_type TEXT NOT NULL,
            applies_to TEXT DEFAULT 'both',
            added_by TEXT DEFAULT 'System',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    
    # Flagged Events
    cursor.execute("""
        CREATE TABLE flagged_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_email TEXT NOT NULL,
            original_session_id TEXT NOT NULL,
            original_record_id TEXT NOT NULL,
            flag_reason TEXT NOT NULL,
            flagged_by TEXT DEFAULT 'System User',
            flagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            original_subject TEXT,
            original_recipients_domain TEXT,
            original_risk_level TEXT,
            original_ml_score REAL
        )
    """)
    
    # Processing Errors
    cursor.execute("""
        CREATE TABLE processing_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            error_type TEXT NOT NULL,
            error_message TEXT NOT NULL,
            error_details TEXT,
            occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved BOOLEAN DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES processing_sessions (id)
        )
    """)
    
    # Risk Factors
    cursor.execute("""
        CREATE TABLE risk_factors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            factor_type TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            threshold REAL,
            description TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    print("✓ All tables created with complete schema")

def verify_schema(db_path):
    """Verify database schema is correct"""
    print("Verifying database schema...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check email_records table has flagging columns
    cursor.execute("PRAGMA table_info(email_records)")
    columns = [column[1] for column in cursor.fetchall()]
    
    required_flagging_columns = [
        'is_flagged', 'flag_reason', 'flagged_at', 'flagged_by', 'previously_flagged'
    ]
    
    missing_columns = []
    for col in required_flagging_columns:
        if col not in columns:
            missing_columns.append(col)
    
    if missing_columns:
        print(f"✗ Missing flagging columns: {missing_columns}")
        return False
    else:
        print("✓ All flagging columns present")
    
    # Check table count
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    expected_tables = [
        'processing_sessions', 'email_records', 'rules', 'whitelist_domains',
        'attachment_keywords', 'flagged_events', 'processing_errors', 'risk_factors'
    ]
    
    missing_tables = []
    for table in expected_tables:
        if table not in tables:
            missing_tables.append(table)
    
    if missing_tables:
        print(f"✗ Missing tables: {missing_tables}")
        return False
    else:
        print(f"✓ All {len(expected_tables)} tables present")
    
    conn.close()
    
    print("✓ Database schema verification passed")
    return True

if __name__ == "__main__":
    if force_recreate_database():
        print("\n=== Database Recreation Complete ===")
        print("Your local database is now ready for Email Guardian")
        print("You can now run: python local_run.py")
    else:
        print("\n=== Database Recreation Failed ===")
        print("Please check the error messages above")