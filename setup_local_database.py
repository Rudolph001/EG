#!/usr/bin/env python3
"""
Setup script for local SQLite database
Ensures database has correct schema for Email Guardian
"""

import os
import sys
import sqlite3
from pathlib import Path

def setup_local_database():
    """Complete setup for local SQLite database"""
    print("=== Email Guardian Local Database Setup ===")
    
    # Database paths to check/setup
    db_paths = [
        "instance/email_guardian.db",
        "email_guardian_local.db",
        "email_guardian.db"
    ]
    
    # Find or create database
    db_path = None
    for path in db_paths:
        if os.path.exists(path):
            db_path = path
            print(f"Found existing database: {path}")
            break
    
    if not db_path:
        # Create new database in instance directory
        Path("instance").mkdir(exist_ok=True)
        db_path = "instance/email_guardian.db"
        print(f"Creating new database: {db_path}")
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        if 'email_records' not in existing_tables:
            print("Creating database tables from scratch...")
            create_all_tables(cursor)
            print("✓ All tables created successfully")
        else:
            print("Database tables exist, checking schema...")
            ensure_schema_updated(cursor)
        
        conn.commit()
        conn.close()
        
        print(f"✓ Local database setup complete: {db_path}")
        print("✓ Database is ready for Email Guardian")
        
        # Set proper permissions
        try:
            os.chmod(db_path, 0o664)
            print("✓ Database permissions set correctly")
        except:
            pass
            
        return True
        
    except Exception as e:
        print(f"✗ Database setup failed: {e}")
        return False

def create_all_tables(cursor):
    """Create all tables with complete schema"""
    
    # Processing Sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_sessions (
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
    
    # Email Records table with all flagging columns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_records (
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
    
    # Rules table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rules (
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
    
    # Whitelist Domains table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS whitelist_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE NOT NULL,
            domain_type TEXT,
            added_by TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    
    # Attachment Keywords table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attachment_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            keyword_type TEXT NOT NULL,
            applies_to TEXT DEFAULT 'both',
            added_by TEXT DEFAULT 'System',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    
    # Flagged Events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS flagged_events (
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
    
    # Processing Errors table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_errors (
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
    
    # Risk Factors table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_factors (
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
    
    print("✓ All database tables created with complete schema")

def ensure_schema_updated(cursor):
    """Ensure existing database has all required columns"""
    
    # Check email_records table schema
    cursor.execute("PRAGMA table_info(email_records)")
    columns = [column[1] for column in cursor.fetchall()]
    
    required_columns = [
        ('is_flagged', 'BOOLEAN DEFAULT 0'),
        ('flag_reason', 'TEXT'),
        ('flagged_at', 'TIMESTAMP'),
        ('flagged_by', 'TEXT'),
        ('previously_flagged', 'BOOLEAN DEFAULT 0')
    ]
    
    added_columns = 0
    for column_name, column_def in required_columns:
        if column_name not in columns:
            try:
                cursor.execute(f"ALTER TABLE email_records ADD COLUMN {column_name} {column_def}")
                print(f"✓ Added missing column: {column_name}")
                added_columns += 1
            except Exception as e:
                print(f"✗ Failed to add column {column_name}: {e}")
    
    if added_columns == 0:
        print("✓ Database schema is up to date")
    else:
        print(f"✓ Added {added_columns} missing columns to database")

if __name__ == "__main__":
    setup_local_database()