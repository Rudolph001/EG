# Email Guardian - macOS Installation Guide

This guide provides instructions for installing and running Email Guardian on macOS.

## Quick Start (macOS)

1. **One-Command Installation:**
   ```bash
   chmod +x install_mac.sh && ./install_mac.sh
   ```

2. **Run the Application:**
   ```bash
   ./run_app_mac.sh
   ```

3. **Open in Browser:**
   Visit `http://localhost:5000`

## Manual Installation (macOS)

### Prerequisites

- macOS 10.14 or later
- Python 3.8 or higher
- Homebrew (will be installed automatically if missing)

### Step-by-Step Installation

1. **Install System Dependencies:**
   ```bash
   # Install Homebrew (if not already installed)
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   
   # Install required packages
   brew install python3 postgresql sqlite3
   ```

2. **Install Python Dependencies:**
   ```bash
   python3 -m pip install --upgrade pip
   python3 -m pip install -r requirements.txt
   ```

3. **Run Setup Script:**
   ```bash
   python3 setup_mac.py
   ```

## Running the Application

### Option 1: Using the Shell Script (Recommended)
```bash
./run_app_mac.sh
```

### Option 2: Using Python Script
```bash
python3 run_mac.py
```

### Option 3: Using Original Script
```bash
python3 run_local.py
```

## Mac-Specific Features

### Files Created for Mac
- `setup_mac.py` - Mac-optimized setup script
- `run_mac.py` - Mac-optimized runner
- `install_mac.sh` - Shell installation script
- `run_app_mac.sh` - Convenient launch script
- `.env.mac` - Mac environment configuration

### Mac Optimizations
- Proper file permissions (755 for directories, 664 for database)
- Homebrew dependency management
- Apple Silicon (M1/M2) compatibility
- macOS security considerations (localhost binding)
- Threaded server for better Mac performance

## Troubleshooting

### Common Issues

1. **Python Not Found:**
   ```bash
   brew install python3
   # Add to PATH if needed
   echo 'export PATH="/opt/homebrew/bin:$PATH"' >> ~/.zprofile
   ```

2. **Permission Denied:**
   ```bash
   chmod +x install_mac.sh
   chmod +x run_app_mac.sh
   ```

3. **Database Errors:**
   ```bash
   rm -f instance/email_guardian.db
   python3 setup_mac.py
   ```

4. **Port Already in Use:**
   ```bash
   # Kill any process using port 5000
   lsof -ti:5000 | xargs kill
   ```

5. **Module Not Found:**
   ```bash
   # Ensure you're in the correct directory
   cd /path/to/email_guardian
   python3 -m pip install -r requirements.txt
   ```

### Performance on Mac

For large datasets (20,000+ records):
- Ensure at least 8GB RAM available
- Close unnecessary applications
- Consider using PostgreSQL instead of SQLite for better performance:
  ```bash
  brew services start postgresql
  # Then configure DATABASE_URL in .env.mac
  ```

### M1/M2 Mac Considerations

- All dependencies are compatible with Apple Silicon
- Homebrew will automatically install ARM64 versions
- Performance is optimized for Apple Silicon architecture

## Development on Mac

### Using Virtual Environments
```bash
python3 -m venv venv_mac
source venv_mac/bin/activate
pip install -r requirements.txt
```

### Debugging
```bash
# Run with debug output
FLASK_DEBUG=true python3 run_mac.py
```

## Uninstallation

To remove Email Guardian from your Mac:

```bash
# Remove application files
rm -rf uploads/ data/ instance/
rm .env.mac run_app_mac.sh

# Remove Homebrew packages (optional)
brew uninstall python3 postgresql sqlite3
```

## Support

- For general issues: Check the main README.md
- For Mac-specific issues: Use this README_MAC.md
- For performance issues: See the performance optimization section in main documentation

## Comparison with Windows Installation

| Feature | Windows | Mac |
|---------|---------|-----|
| Setup Script | `local_setup.py` | `setup_mac.py` |
| Runner | `run_local.py` | `run_mac.py` |
| Shell Script | N/A | `install_mac.sh` |
| Environment | `.env` | `.env.mac` |
| Package Manager | pip | Homebrew + pip |
| Permissions | Windows ACL | Unix permissions |

Both installations maintain the same functionality and database compatibility.