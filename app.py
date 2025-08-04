
import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "local-dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure the database - default to local SQLite
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    # For local development, use current directory for better permissions
    db_file_path = os.path.join(os.getcwd(), "email_guardian_local.db")
    database_url = f"sqlite:///{db_file_path}"
    print(f"Using local SQLite database: {db_file_path}")

# Ensure database file can be created for SQLite
if database_url.startswith('sqlite:///'):
    db_path = database_url.replace('sqlite:///', '')
    
    try:
        # Ensure parent directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, mode=0o755, exist_ok=True)
        
        # Test database creation/access
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS test_connection (id INTEGER)")
        conn.commit()
        conn.close()
        print(f"✓ Database accessible: {db_path}")
        
    except Exception as e:
        print(f"✗ Database setup error: {e}")
        # Fallback to memory database for development
        print("Falling back to in-memory database for this session...")
        database_url = "sqlite:///:memory:"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Initialize the app with the extension
db.init_app(app)

# Ensure directories exist with proper permissions
for directory in ['uploads', 'data', 'static/css', 'static/js', 'templates']:
    os.makedirs(directory, mode=0o755, exist_ok=True)

with app.app_context():
    # Import models and routes
    import models
    import routes
    
    # Create all tables
    try:
        # Test database connection first
        result = db.session.execute(db.text("SELECT 1"))
        result.close()
        
        # Create tables
        db.create_all()
        db.session.commit()
        print("✓ Database tables created successfully")
    except Exception as e:
        print(f"✗ Failed to create database tables: {e}")
        db.session.rollback()
        
        # Try to recreate database file
        print("Attempting to recreate database...")
        try:
            db_path = database_url.replace('sqlite:///', '')
            if os.path.exists(db_path):
                os.remove(db_path)
            
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.close()
            os.chmod(db_path, 0o664)
            
            # Try creating tables again
            db.create_all()
            db.session.commit()
            print("✓ Database recreated and tables created successfully")
        except Exception as e2:
            print(f"✗ Failed to recreate database: {e2}")
            raise
