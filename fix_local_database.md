# Fix Local Database Schema

If you're getting the error about `is_flagged` column missing when running locally, this means your local SQLite database has an older schema. Here are two ways to fix it:

## Option 1: Delete and Recreate Database (Recommended)
```bash
# Delete the old database file
rm instance/email_guardian.db
rm email_guardian_local.db  # if this exists instead

# Run the app - it will create a new database with the correct schema
python local_run.py
# or
python main.py
```

## Option 2: Run Migration Script
```bash
# Run the migration script to add missing columns
python migrate_local_db.py
```

## Option 3: Manual SQLite Fix
If you want to keep your existing data, manually add the columns:

```sql
-- Connect to your SQLite database and run these commands:
ALTER TABLE email_records ADD COLUMN is_flagged BOOLEAN DEFAULT 0;
ALTER TABLE email_records ADD COLUMN flag_reason TEXT;
ALTER TABLE email_records ADD COLUMN flagged_at TIMESTAMP;
ALTER TABLE email_records ADD COLUMN flagged_by TEXT;
ALTER TABLE email_records ADD COLUMN previously_flagged BOOLEAN DEFAULT 0;
```

## Timestamp Format Support
Your timestamp format `2025-08-04T23:58:20.543+0200` is now fully supported. The enhanced parser handles:
- Milliseconds (.543)
- Timezone information (+0200)
- Malformed timestamps with data quality issues

The error you encountered should be completely resolved once your local database has the correct schema.