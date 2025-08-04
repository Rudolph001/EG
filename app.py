
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
    database_url = "sqlite:///instance/email_guardian.db"

# Create the database file if it doesn't exist
db_path = database_url.replace('sqlite:///', '')
if not os.path.exists(db_path):
    import sqlite3
    try:
        # Create the database file
        conn = sqlite3.connect(db_path)
        conn.close()
        print(f"✓ Created database file: {db_path}")
    except Exception as e:
        print(f"✗ Failed to create database file: {e}")

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
        db.create_all()
        print("✓ Database tables created successfully")
    except Exception as e:
        print(f"✗ Failed to create database tables: {e}")
