# Database Schema Synchronization Guide

## ⚠️ CRITICAL REQUIREMENT

**ALL database schema changes must be applied to BOTH PostgreSQL and SQLite databases**

Email Guardian uses a dual database architecture:
- **PostgreSQL**: Production environment (Replit)  
- **SQLite**: Local development environment

## Schema Change Workflow

When making any database changes (adding columns, modifying tables, etc.):

### 1. PostgreSQL (Production) Changes
```sql
-- Use execute_sql_tool in Replit
ALTER TABLE email_records ADD COLUMN new_column_name VARCHAR(255);
```

### 2. SQLite (Local) Changes
```python
# Add to local database
import sqlite3
conn = sqlite3.connect('instance/email_guardian.db')
cursor = conn.cursor()
cursor.execute('ALTER TABLE email_records ADD COLUMN new_column_name TEXT')
conn.commit()
conn.close()
```

### 3. Update Models (if needed)
```python
# Update models.py if new columns are added
class EmailRecord(db.Model):
    # ... existing columns
    new_column_name = db.Column(db.String(255))
```

## Synchronization Tools

### Complete Setup
```bash
# Recreate local database from scratch
python force_recreate_local_db.py
```

### Migration Only
```bash
# Add missing columns to existing database
python migrate_local_db.py
```

### Schema Verification
```bash
# Check local database schema
python -c "
import sqlite3
conn = sqlite3.connect('instance/email_guardian.db')
cursor = conn.cursor()
cursor.execute('PRAGMA table_info(email_records)')
print([row[1] for row in cursor.fetchall()])
conn.close()
"
```

## Recent Schema History

### 2025-08-06: Fixed Schema Mismatch
- **Issue**: `account_type` column missing from PostgreSQL  
- **Fix**: Added to both PostgreSQL and SQLite
- **Tools**: `execute_sql_tool` + Python script

### 2025-08-06: Added Flagging Columns
- **Columns**: `is_flagged`, `flag_reason`, `flagged_at`, `flagged_by`, `previously_flagged`
- **Reason**: Support email flagging functionality
- **Applied**: Both databases

### 2025-08-06: Enhanced Timestamp Support
- **Format**: `2025-08-04T23:58:20.543+0200`
- **Features**: Milliseconds + timezone parsing
- **Impact**: Data processing pipeline

## Error Prevention

### Common Errors
1. **"column does not exist"** → Schema mismatch between databases
2. **"table email_records has no column named X"** → Missing column in one database
3. **Processing failures** → Timestamp parsing or missing fields

### Prevention Checklist
- [ ] Applied change to PostgreSQL
- [ ] Applied change to SQLite  
- [ ] Updated models.py if needed
- [ ] Tested both local and production
- [ ] Updated this documentation

## Emergency Recovery

If local database becomes corrupted or out of sync:

```bash
# Nuclear option - complete recreation
python force_recreate_local_db.py

# Verify everything works
python local_run.py
```

Remember: **Schema consistency between environments is critical for application stability.**