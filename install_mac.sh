#!/bin/bash

# Email Guardian Mac Installation Script
# Run this script to install and set up Email Guardian on macOS

echo "=== Email Guardian Mac Installation ==="
echo ""

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "⚠ Warning: This script is designed for macOS"
fi

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check and install Homebrew
echo "Checking Homebrew installation..."
if ! command_exists brew; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Add Homebrew to PATH for M1 Macs
    if [[ -f "/opt/homebrew/bin/brew" ]]; then
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
else
    echo "✓ Homebrew is installed"
fi

# Update Homebrew
echo "Updating Homebrew..."
brew update

# Install system dependencies
echo "Installing system dependencies..."
brew install python3 postgresql sqlite3

# Verify Python installation
echo "Checking Python installation..."
if ! command_exists python3; then
    echo "✗ Python3 not found. Please install Python 3.8+"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✓ Python $PYTHON_VERSION detected"

# Install Python dependencies
echo "Installing Python dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

# Create necessary directories
echo "Creating directories..."
mkdir -p uploads data instance static/css static/js templates
chmod 755 uploads data instance static

# Set up database
echo "Setting up database..."
touch instance/email_guardian.db
chmod 664 instance/email_guardian.db

# Create Mac environment file
echo "Creating Mac environment file..."
cat > .env.mac << EOL
# Email Guardian Mac Configuration
FLASK_ENV=development
FLASK_DEBUG=true
SESSION_SECRET=local-dev-secret-key-change-in-production-mac
DATABASE_URL=sqlite:///instance/email_guardian.db
FAST_MODE=true
CHUNK_SIZE=1000
MAX_ML_RECORDS=5000
PYTHONPATH=\${PYTHONPATH}:.
EOL

# Create convenient run script
echo "Creating run script..."
cat > run_app_mac.sh << 'EOL'
#!/bin/bash
# Email Guardian Mac Runner

echo "=== Starting Email Guardian on Mac ==="

# Source environment
if [ -f ".env.mac" ]; then
    export $(cat .env.mac | grep -v '^#' | xargs)
fi

# Start the application
echo "✓ Starting server on http://localhost:5000"
echo "✓ Press Ctrl+C to stop"
echo ""

python3 run_mac.py
EOL

chmod +x run_app_mac.sh

# Run basic configuration
echo "Setting up basic configuration..."
if [ -f "setup_basic_config.py" ]; then
    python3 setup_basic_config.py
fi

echo ""
echo "=== Mac Installation Complete! ==="
echo ""
echo "To run Email Guardian:"
echo "1. Run: ./run_app_mac.sh"
echo "   OR"
echo "2. Run: python3 run_mac.py"
echo "   OR"
echo "3. Run: python3 setup_mac.py (for full setup)"
echo ""
echo "Then open: http://localhost:5000"
echo ""
echo "Mac-specific files created:"
echo "  - .env.mac (environment configuration)"
echo "  - run_app_mac.sh (launch script)"
echo "  - Homebrew dependencies installed"
echo ""
echo "For troubleshooting, check the README_MAC.md file"