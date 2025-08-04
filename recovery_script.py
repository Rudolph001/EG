
#!/usr/bin/env python3
"""
Recovery script for Email Guardian stuck processing sessions
Helps recover and restart failed or stuck upload processes
"""

import os
import sys
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

def setup_environment():
    """Setup environment for recovery"""
    os.environ.setdefault('FLASK_ENV', 'development')
    os.environ.setdefault('SESSION_SECRET', 'local-dev-secret-key')
    
    # Use absolute path for SQLite database
    db_file_path = os.path.abspath("instance/email_guardian.db")
    os.environ.setdefault('DATABASE_URL', f'sqlite:///{db_file_path}')
    
    os.environ.setdefault('FAST_MODE', 'true')
    os.environ.setdefault('CHUNK_SIZE', '500')  # Smaller chunks for recovery
    os.environ.setdefault('MAX_ML_RECORDS', '2000')

def recover_stuck_sessions():
    """Recover stuck processing sessions"""
    try:
        from app import app
        from models import ProcessingSession, db
        from data_processor import DataProcessor
        
        with app.app_context():
            print("=== Email Guardian Recovery Tool ===")
            
            # Find stuck sessions
            stuck_sessions = ProcessingSession.query.filter_by(status='processing').all()
            
            if not stuck_sessions:
                print("✓ No stuck sessions found")
                return
            
            print(f"Found {len(stuck_sessions)} stuck sessions:")
            
            for i, session in enumerate(stuck_sessions, 1):
                print(f"{i}. Session {session.id[:8]}... - {session.filename}")
                print(f"   Processed: {session.processed_records or 0}/{session.total_records or 'Unknown'}")
                print(f"   Current stage: {session.current_stage or 'Unknown'}")
                print()
            
            # Ask user which session to recover
            try:
                choice = input("Enter session number to recover (or 'all' for all): ").strip()
                
                if choice.lower() == 'all':
                    sessions_to_recover = stuck_sessions
                else:
                    session_idx = int(choice) - 1
                    if 0 <= session_idx < len(stuck_sessions):
                        sessions_to_recover = [stuck_sessions[session_idx]]
                    else:
                        print("Invalid session number")
                        return
                
                # Recover selected sessions
                processor = DataProcessor()
                
                for session in sessions_to_recover:
                    print(f"\nRecovering session {session.id[:8]}...")
                    
                    try:
                        # Reset session status if needed
                        if session.error_message:
                            print(f"Previous error: {session.error_message}")
                            session.error_message = None
                        
                        # Check if file still exists
                        if session.data_path and os.path.exists(session.data_path):
                            print(f"Resuming processing from file: {session.data_path}")
                            processor.process_csv(session.id, session.data_path)
                            print(f"✓ Session {session.id[:8]} recovered successfully")
                        else:
                            print(f"✗ Data file not found: {session.data_path}")
                            session.status = 'error'
                            session.error_message = "Data file not found"
                            db.session.commit()
                    
                    except Exception as e:
                        print(f"✗ Failed to recover session {session.id[:8]}: {str(e)}")
                        session.status = 'error'
                        session.error_message = f"Recovery failed: {str(e)}"
                        db.session.commit()
                        
            except ValueError:
                print("Invalid input")
                return
            except KeyboardInterrupt:
                print("\nRecovery cancelled")
                return
                
    except Exception as e:
        print(f"✗ Recovery failed: {str(e)}")

def cleanup_old_sessions():
    """Clean up old completed or failed sessions"""
    try:
        from app import app
        from models import ProcessingSession, EmailRecord, db
        from datetime import datetime, timedelta
        
        with app.app_context():
            print("\n=== Cleanup Old Sessions ===")
            
            # Find old sessions (older than 7 days)
            cutoff_date = datetime.utcnow() - timedelta(days=7)
            old_sessions = ProcessingSession.query.filter(
                ProcessingSession.upload_time < cutoff_date
            ).all()
            
            if not old_sessions:
                print("✓ No old sessions to cleanup")
                return
            
            print(f"Found {len(old_sessions)} old sessions to cleanup")
            
            choice = input("Delete old sessions and their data? (y/N): ").strip().lower()
            
            if choice == 'y':
                for session in old_sessions:
                    try:
                        # Delete associated email records
                        EmailRecord.query.filter_by(session_id=session.id).delete()
                        
                        # Delete session
                        db.session.delete(session)
                        
                        # Delete uploaded file if exists
                        if session.data_path and os.path.exists(session.data_path):
                            os.remove(session.data_path)
                            
                        print(f"✓ Cleaned up session {session.id[:8]}...")
                        
                    except Exception as e:
                        print(f"✗ Failed to cleanup session {session.id[:8]}: {str(e)}")
                
                db.session.commit()
                print("✓ Cleanup completed")
            else:
                print("Cleanup cancelled")
                
    except Exception as e:
        print(f"✗ Cleanup failed: {str(e)}")

def main():
    """Main recovery function"""
    setup_environment()
    
    print("1. Recover stuck sessions")
    print("2. Cleanup old sessions")
    print("3. Both")
    
    choice = input("Select option (1-3): ").strip()
    
    if choice == '1':
        recover_stuck_sessions()
    elif choice == '2':
        cleanup_old_sessions()
    elif choice == '3':
        recover_stuck_sessions()
        cleanup_old_sessions()
    else:
        print("Invalid choice")

if __name__ == "__main__":
    main()
