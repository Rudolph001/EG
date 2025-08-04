
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
    # Ensure instance directory exists
    os.makedirs('instance', exist_ok=True)
    # Use absolute path for SQLite
    db_file_path = os.path.abspath("instance/email_guardian.db")
    database_url = f"sqlite:///{db_file_path}"

# Ensure database file and directory exist with proper permissions
if database_url.startswith('sqlite:///'):
    db_path = database_url.replace('sqlite:///', '')
    db_dir = os.path.dirname(db_path)
    
    try:
        # Create directory with proper permissions
        os.makedirs(db_dir, mode=0o755, exist_ok=True)
        
        # Create database file if it doesn't exist
        if not os.path.exists(db_path):
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE IF NOT EXISTS test_table (id INTEGER)")
            conn.commit()
            conn.close()
            # Set proper file permissions
            os.chmod(db_path, 0o664)
            print(f"✓ Created database file: {db_path}")
        else:
            # Test existing database file
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("SELECT 1")
            conn.close()
            print(f"✓ Database file accessible: {db_path}")
            
    except Exception as e:
        print(f"✗ Database setup error: {e}")
        # Try to recreate the database file
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE IF NOT EXISTS test_table (id INTEGER)")
            conn.commit()
            conn.close()
            os.chmod(db_path, 0o664)
            print(f"✓ Recreated database file: {db_path}")
        except Exception as e2:
            print(f"✗ Failed to recreate database: {e2}")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Initialize the app with the extension
db.init_app(app)

# Ensure directories exist
os.makedirs('uploads', exist_ok=True)
os.makedirs('data', exist_ok=True)
os.makedirs('instance', exist_ok=True)

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
