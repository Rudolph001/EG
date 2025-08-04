from app import app

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
#!/usr/bin/env python3
"""
Main entry point for Email Guardian application
"""

from app import app

if __name__ == "__main__":
    app.run(
        debug=True,
        host='0.0.0.0',
        port=5000
    )
