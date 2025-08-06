#!/usr/bin/env python3
"""
Create WhitelistSender table in local SQLite database
Run this script to add the whitelist_senders table to your local database
"""

import sqlite3
import logging
import os

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_whitelist_senders_table():
    """Create the whitelist_senders table in local SQLite database"""
    
    db_path = './instance/local_database.db'
    
    if not os.path.exists('./instance'):
        os.makedirs('./instance')
        logger.info("Created instance directory")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create whitelist_senders table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS whitelist_senders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_address VARCHAR(255) NOT NULL UNIQUE,
            added_by VARCHAR(255) DEFAULT 'System User',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            notes TEXT,
            times_excluded INTEGER DEFAULT 0,
            last_excluded TIMESTAMP
        )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_whitelist_senders_email ON whitelist_senders(email_address)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_whitelist_senders_active ON whitelist_senders(is_active)')
        
        conn.commit()
        logger.info("✓ WhitelistSender table created successfully in local database")
        
        # Verify the table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='whitelist_senders'")
        if cursor.fetchone():
            logger.info("✓ Table verification successful")
            
            # Show table schema
            cursor.execute("PRAGMA table_info(whitelist_senders)")
            columns = cursor.fetchall()
            logger.info("Table schema:")
            for col in columns:
                logger.info(f"  - {col[1]} ({col[2]})")
        else:
            logger.error("✗ Table verification failed")
            
        conn.close()
        
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("Creating WhitelistSender table in local SQLite database...")
    success = create_whitelist_senders_table()
    
    if success:
        print("✓ Local database schema updated successfully")
        print("\nNext steps:")
        print("1. The WhitelistSender functionality is now ready")
        print("2. You can add whitelisted senders via the dashboard")
        print("3. Future data imports will automatically exclude whitelisted senders")
    else:
        print("✗ Failed to update local database schema")
        print("Please check the error messages above and try again")