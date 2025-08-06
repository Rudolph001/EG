# Email Guardian - Local Setup Guide

## Quick Local Setup

Your local SQLite database has been completely recreated with the correct schema. The "is_flagged column missing" error is now fixed.

### Running Locally

```bash
# Option 1: Use the local runner (recommended)
python local_run.py

# Option 2: Use the standard runner  
python main.py
```

### Database Status

✓ **Database Location**: `instance/email_guardian.db`  
✓ **Schema**: Complete with all flagging columns  
✓ **Timestamp Support**: Your format `2025-08-04T23:58:20.543+0200` is fully supported  
✓ **Tables**: All 8 tables created with proper relationships  

### What Was Fixed

1. **Schema Mismatch**: Local SQLite now matches production PostgreSQL exactly
2. **Missing Columns**: All flagging columns (`is_flagged`, `flag_reason`, etc.) are present
3. **Timestamp Parsing**: Enhanced parser handles milliseconds and timezones
4. **Database Recreation**: Old corrupted database removed, new one created from scratch

### File Processing

Your CSV files with timestamps like `2025-08-04T23:58:20.543+0200` will now process correctly through all 9 stages:

1. **Data Ingestion** - CSV parsing with enhanced timestamp support
2. **Data Validation** - Quality checks and sanitization  
3. **Domain Classification** - Automated domain categorization
4. **Pre-processing Exclusions** - Rule-based filtering
5. **Risk Keywords Analysis** - Attachment and subject scanning
6. **Exclusion Keywords Analysis** - Negative pattern detection  
7. **Rule Engine Processing** - Business logic application
8. **ML Risk Assessment** - Advanced analytics and scoring
9. **Final Categorization** - Risk level assignment

### Troubleshooting

If you encounter any database issues:

```bash
# Force recreate database (will delete existing data)
python force_recreate_local_db.py

# Check database schema
python -c "
import sqlite3
conn = sqlite3.connect('instance/email_guardian.db')
cursor = conn.cursor()
cursor.execute('PRAGMA table_info(email_records)')
print([row[1] for row in cursor.fetchall()])
conn.close()
"
```

The database schema issue that was causing processing failures is now completely resolved.