
# Email Guardian - Local Setup Guide

This guide helps you run Email Guardian on your local machine with SQLite database.

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

## Quick Start

1. **Run the setup script:**
   ```bash
   python local_setup.py
   ```

2. **Start the application:**
   ```bash
   python local_run.py
   ```
   
   Or use the simple runner:
   ```bash
   python run_local.py
   ```

3. **Open your browser to:** http://localhost:5000

## What Gets Set Up

- **SQLite Database**: Located at `instance/email_guardian.db`
- **Upload Directory**: `uploads/` for CSV files
- **Data Directory**: `data/` for session data
- **Basic Configuration**: Sample rules, domains, and keywords

## Manual Setup (Alternative)

If the setup script doesn't work:

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Create Directories
```bash
mkdir uploads data instance
```

### 3. Set Environment Variables

**Windows:**
```cmd
set FLASK_ENV=development
set DATABASE_URL=sqlite:///instance/email_guardian.db
```

**Mac/Linux:**
```bash
export FLASK_ENV=development
export DATABASE_URL=sqlite:///instance/email_guardian.db
```

### 4. Run the Application
```bash
python local_run.py
```

## File Structure

```
email-guardian/
├── local_setup.py          # Setup script
├── local_run.py            # Development runner
├── run_local.py            # Simple runner
├── app.py                  # Flask app configuration
├── models.py               # Database models
├── routes.py               # Web routes
├── uploads/                # File upload directory
├── data/                   # Session data storage
├── instance/               # SQLite database location
│   └── email_guardian.db   # SQLite database file
└── requirements.txt        # Python dependencies
```

## Database

The application uses SQLite by default for local development:
- **Location**: `instance/email_guardian.db`
- **No additional setup required**
- **Automatically created on first run**

## Configuration Files

- **`.env`**: Created automatically by setup script
- **`requirements.txt`**: Python dependencies
- **`setup_basic_config.py`**: Populates database with sample data

## Troubleshooting

### Common Issues

1. **Port 5000 in use**: Change port in `local_run.py`
2. **Database errors**: Delete `instance/email_guardian.db` and restart
3. **Import errors**: Run `python local_setup.py` again
4. **Permission errors**: Ensure you have write access to the directory

### Performance

- Application runs in fast mode by default for local development
- Processing is optimized for smaller datasets
- Use SSD storage for better performance with large CSV files

## Features Available Locally

- **CSV Upload & Processing**: Full email data analysis
- **ML Risk Analysis**: Machine learning threat detection
- **Domain Management**: Whitelist and categorization
- **Case Management**: Investigation workflows
- **Real-time Dashboards**: Analytics and visualizations
- **Rule Engine**: Custom security rules

## Data Privacy

- All processing happens locally on your machine
- No external server connections required
- Data stored in local SQLite database
- CSV files remain on your local system

## Support

For local setup issues:
1. Verify Python 3.8+ is installed
2. Check that all dependencies installed successfully
3. Ensure write permissions in application directory
4. Review console output for specific error messages
