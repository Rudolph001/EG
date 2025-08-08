
#!/usr/bin/env python3
"""
Migration script to add match_condition column to attachment_keywords table
"""

import sqlite3
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_match_conditions():
    """Add match_condition column to attachment_keywords table"""
    try:
        # Connect to local database
        conn = sqlite3.connect('email_guardian_local.db')
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(attachment_keywords)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'match_condition' in columns:
            logger.info("match_condition column already exists")
            return True
        
        # Add match_condition column with default value
        cursor.execute("""
            ALTER TABLE attachment_keywords 
            ADD COLUMN match_condition TEXT DEFAULT 'contains'
        """)
        
        # Update existing records to have default match_condition
        cursor.execute("""
            UPDATE attachment_keywords 
            SET match_condition = 'contains' 
            WHERE match_condition IS NULL
        """)
        
        conn.commit()
        logger.info("Successfully added match_condition column to attachment_keywords")
        
        # Verify the migration
        cursor.execute("SELECT COUNT(*) FROM attachment_keywords WHERE match_condition = 'contains'")
        count = cursor.fetchone()[0]
        logger.info(f"Updated {count} existing records with default match_condition")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Error migrating match_conditions: {str(e)}")
        return False

if __name__ == "__main__":
    migrate_match_conditions()
