import pandas as pd
import csv
import json
import logging
from datetime import datetime
from models import ProcessingSession, EmailRecord, ProcessingError
from session_manager import SessionManager
from rule_engine import RuleEngine
from domain_manager import DomainManager
from ml_engine import MLEngine
from performance_config import config
from app import db

logger = logging.getLogger(__name__)

class DataProcessor:
    """Handles CSV processing and workflow engine"""
    
    def __init__(self):
        self.chunk_size = config.chunk_size
        self.session_manager = SessionManager()
        self.rule_engine = RuleEngine()
        self.domain_manager = DomainManager()
        self.ml_engine = MLEngine()
        self.enable_fast_mode = config.fast_mode
        logger.info(f"DataProcessor initialized with config: {config.get_config_summary()}")
        
        # Expected CSV columns (case-insensitive matching)
        self.expected_columns = [
            '_time', 'sender', 'subject', 'attachments', 'recipients',
            'recipients_email_domain', 'leaver', 'termination_date',
            'wordlist_attachment', 'wordlist_subject', 'bunit',
            'department', 'status', 'user_response', 'final_outcome',
            'justification', 'policy_name'
        ]
    
    def process_csv(self, session_id, file_path):
        """Main CSV processing workflow"""
        try:
            logger.info(f"Starting CSV processing for session {session_id}")
            
            # Check if session is already being processed (prevent race conditions)
            session = ProcessingSession.query.get(session_id)
            if not session:
                logger.error(f"Session {session_id} not found")
                return
                
            if session.status == 'processing' and session.processed_records > 0:
                logger.warning(f"Session {session_id} is already being processed with {session.processed_records} records, skipping")
                return
                
            if session.status == 'completed':
                logger.info(f"Session {session_id} is already completed, skipping")
                return
            
            # Update session status atomically
            session.status = 'processing'
            db.session.commit()
            
            # Step 1: Validate CSV structure (quick validation)
            column_mapping = self._validate_csv_structure(file_path)
            
            # Step 2: Count total records (optimized)
            total_records = self._count_csv_rows(file_path)
            if session:
                session.total_records = total_records
                db.session.commit()
            
            processed_count = 0
            
            # Use optimized chunk size for performance
            chunk_size = self.chunk_size if self.enable_fast_mode else min(500, self.chunk_size)
            
            # Calculate total chunks
            total_chunks = (total_records + chunk_size - 1) // chunk_size  # Round up division
            current_chunk = 0
            
            # Process file in chunks
            for chunk_df in pd.read_csv(file_path, chunksize=chunk_size):
                try:
                    current_chunk += 1
                    chunk_processed = self._process_chunk(session_id, chunk_df, column_mapping, processed_count)
                    processed_count += chunk_processed
                    
                    # Update progress with chunk information
                    if session:
                        session.processed_records = processed_count
                        session.current_chunk = current_chunk
                        session.total_chunks = total_chunks
                        db.session.commit()
                    
                    logger.info(f"Completed chunk {current_chunk}/{total_chunks} - {chunk_processed} records processed")
                    
                    # Update progress based on configuration
                    if processed_count % config.progress_update_interval == 0:
                        logger.info(f"Progress update: {processed_count}/{total_records} records processed")
                        
                except Exception as chunk_error:
                    logger.warning(f"Error processing chunk {current_chunk}: {str(chunk_error)}")
                    continue  # Skip problematic chunks but continue processing
            
            # Step 3: Apply 4-step workflow with robust error handling
            try:
                self._apply_workflow(session_id)
            except Exception as workflow_error:
                logger.warning(f"Workflow error for session {session_id}: {str(workflow_error)}")
                # Continue to completion even if workflow has issues
                if session:
                    session.error_message = f"Workflow warning: {str(workflow_error)}"
            
            # Mark as completed
            if session:
                session.status = 'completed'
                session.processed_records = processed_count
                db.session.commit()
            
            logger.info(f"CSV processing completed for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error processing CSV for session {session_id}: {str(e)}")
            session = ProcessingSession.query.get(session_id)
            if session:
                session.status = 'error'
                session.error_message = str(e)
                db.session.commit()
            db.session.commit()
            raise
    
    def _validate_csv_structure(self, file_path):
        """Validate CSV structure and create column mapping"""
        try:
            # Read first few rows to check structure
            sample_df = pd.read_csv(file_path, nrows=5)
            actual_columns = [col.lower().strip() for col in sample_df.columns]
            
            # Create case-insensitive column mapping
            column_mapping = {}
            missing_columns = []
            
            for expected_col in self.expected_columns:
                found = False
                for actual_col in sample_df.columns:
                    if actual_col.lower().strip() == expected_col.lower():
                        column_mapping[expected_col] = actual_col
                        found = True
                        break
                
                if not found:
                    missing_columns.append(expected_col)
            
            # Log missing columns but don't fail
            if missing_columns:
                logger.warning(f"Missing columns: {missing_columns}")
            
            logger.info(f"CSV validation successful. Column mapping: {column_mapping}")
            return column_mapping
            
        except Exception as e:
            logger.error(f"CSV validation failed: {str(e)}")
            raise ValueError(f"Invalid CSV format: {str(e)}")
    
    def _count_csv_rows(self, file_path):
        """Count total rows in CSV file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                row_count = sum(1 for row in reader) - 1  # Exclude header
            return max(0, row_count)
        except Exception as e:
            logger.error(f"Error counting CSV rows: {str(e)}")
            return 0
    
    def _process_chunk(self, session_id, chunk_df, column_mapping, start_index):
        """Process a chunk of CSV data"""
        try:
            processed_count = 0
            
            for index, row in chunk_df.iterrows():
                try:
                    # Create unique record ID
                    record_id = f"{session_id}_{start_index + processed_count}"
                    
                    # Map columns and normalize data
                    record_data = {}
                    for expected_col, actual_col in column_mapping.items():
                        if actual_col in row:
                            value = row[actual_col]
                            # Convert to string but preserve original case for rule matching
                            if pd.notna(value):
                                record_data[expected_col] = str(value).strip()
                            else:
                                record_data[expected_col] = ''
                    
                    # Create EmailRecord
                    email_record = EmailRecord(
                        session_id=session_id,
                        record_id=record_id,
                        time=record_data.get('_time', ''),
                        sender=record_data.get('sender', ''),
                        subject=record_data.get('subject', ''),
                        attachments=record_data.get('attachments', ''),
                        recipients=record_data.get('recipients', ''),
                        recipients_email_domain=record_data.get('recipients_email_domain', ''),
                        leaver=record_data.get('leaver', ''),
                        termination_date=record_data.get('termination_date', ''),
                        wordlist_attachment=record_data.get('wordlist_attachment', ''),
                        wordlist_subject=record_data.get('wordlist_subject', ''),
                        bunit=record_data.get('bunit', ''),
                        department=record_data.get('department', ''),
                        status=record_data.get('status', ''),
                        user_response=record_data.get('user_response', ''),
                        final_outcome=record_data.get('final_outcome', ''),
                        justification=record_data.get('justification', ''),
                        policy_name=record_data.get('policy_name', '')
                    )
                    
                    db.session.add(email_record)
                    processed_count += 1
                    
                except Exception as e:
                    # Log individual record errors
                    error = ProcessingError(
                        session_id=session_id,
                        error_type='record_processing',
                        error_message=str(e),
                        record_data={'index': index, 'data': row.to_dict()}
                    )
                    db.session.add(error)
                    logger.warning(f"Error processing record at index {index}: {str(e)}")
            
            # Commit chunk with error handling
            try:
                db.session.commit()
                logger.info(f"Processed chunk: {processed_count} records")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error committing chunk: {str(e)}")
                raise
            return processed_count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing chunk: {str(e)}")
            raise
    
    def _apply_workflow(self, session_id):
        """Apply 4-step processing workflow with robust error handling"""
        try:
            logger.info(f"Applying workflow for session {session_id}")
            
            # Step 1: Apply Exclusion Rules
            try:
                self._apply_exclusion_rules(session_id)
                logger.info(f"Step 1 completed: Exclusion rules applied for session {session_id}")
            except Exception as e:
                logger.warning(f"Step 1 failed for session {session_id}: {str(e)}")
            
            # Step 2: Apply Whitelist Filtering
            try:
                self._apply_whitelist_filtering(session_id)
                logger.info(f"Step 2 completed: Whitelist filtering applied for session {session_id}")
            except Exception as e:
                logger.warning(f"Step 2 failed for session {session_id}: {str(e)}")
            
            # Step 3: Apply Security Rules
            try:
                self._apply_security_rules(session_id)
                logger.info(f"Step 3 completed: Security rules applied for session {session_id}")
            except Exception as e:
                logger.warning(f"Step 3 failed for session {session_id}: {str(e)}")
            
            # Step 4: Apply ML Analysis
            try:
                self._apply_ml_analysis(session_id)
                logger.info(f"Step 4 completed: ML analysis applied for session {session_id}")
            except Exception as e:
                logger.warning(f"Step 4 failed for session {session_id}: {str(e)}")
            
            logger.info(f"Workflow completed for session {session_id}")
            
        except Exception as e:
            logger.error(f"Critical error applying workflow for session {session_id}: {str(e)}")
            raise
    
    def _apply_exclusion_rules(self, session_id):
        """Step 1: Apply exclusion rules to filter records"""
        try:
            logger.info(f"Applying exclusion rules for session {session_id}")
            
            # Get all active exclusion rules
            excluded_count = self.rule_engine.apply_exclusion_rules(session_id)
            
            # Update session
            session = ProcessingSession.query.get(session_id)
            if session:
                session.exclusion_applied = True
                db.session.commit()
            
            logger.info(f"Exclusion rules applied: {excluded_count} records excluded")
            
        except Exception as e:
            logger.error(f"Error applying exclusion rules: {str(e)}")
            raise
    
    def _apply_whitelist_filtering(self, session_id):
        """Step 2: Apply whitelist filtering"""
        try:
            logger.info(f"Applying whitelist filtering for session {session_id}")
            
            whitelisted_count = self.domain_manager.apply_whitelist_filtering(session_id)
            
            # Update session
            session = ProcessingSession.query.get(session_id)
            if session:
                session.whitelist_applied = True
                db.session.commit()
            
            logger.info(f"Whitelist filtering applied: {whitelisted_count} records whitelisted")
            
        except Exception as e:
            logger.error(f"Error applying whitelist filtering: {str(e)}")
            raise
    
    def _apply_security_rules(self, session_id):
        """Step 3: Apply security rules"""
        try:
            logger.info(f"Applying security rules for session {session_id}")
            
            rule_matches = self.rule_engine.apply_security_rules(session_id)
            
            # Update session
            session = ProcessingSession.query.get(session_id)
            if session:
                session.rules_applied = True
                db.session.commit()
            
            logger.info(f"Security rules applied: {len(rule_matches)} rule matches found")
            
        except Exception as e:
            logger.error(f"Error applying security rules: {str(e)}")
            raise
    
    def _apply_ml_analysis(self, session_id):
        """Step 4: Apply ML analysis"""
        try:
            logger.info(f"Applying ML analysis for session {session_id}")
            
            # Only analyze non-whitelisted records
            analysis_results = self.ml_engine.analyze_session(session_id)
            
            # Update session
            session = ProcessingSession.query.get(session_id)
            if session:
                session.ml_applied = True
                session.processing_stats = analysis_results.get('processing_stats', {})
                db.session.commit()
            
            logger.info(f"ML analysis completed for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error applying ML analysis: {str(e)}")
            raise
    
    def reprocess_session(self, session_id, skip_stages=None):
        """Reprocess a session with updated rules"""
        try:
            skip_stages = skip_stages or []
            
            logger.info(f"Reprocessing session {session_id}, skipping stages: {skip_stages}")
            
            # Reset processing flags
            session = ProcessingSession.query.get(session_id)
            if session and 'exclusion' not in skip_stages:
                session.exclusion_applied = False
                # Clear exclusion results
                EmailRecord.query.filter_by(session_id=session_id).update({
                    'excluded_by_rule': None
                })
            
            if session and 'whitelist' not in skip_stages:
                session.whitelist_applied = False
                # Clear whitelist results
                EmailRecord.query.filter_by(session_id=session_id).update({
                    'whitelisted': False
                })
            
            if session and 'rules' not in skip_stages:
                session.rules_applied = False
                # Clear rule matches
                EmailRecord.query.filter_by(session_id=session_id).update({
                    'rule_matches': None
                })
            
            if session and 'ml' not in skip_stages:
                session.ml_applied = False
                # Clear ML results
                EmailRecord.query.filter_by(session_id=session_id).update({
                    'ml_risk_score': None,
                    'ml_anomaly_score': None,
                    'risk_level': None,
                    'ml_explanation': None
                })
            
            db.session.commit()
            
            # Apply workflow again
            self._apply_workflow(session_id)
            
            logger.info(f"Session {session_id} reprocessed successfully")
            
        except Exception as e:
            logger.error(f"Error reprocessing session {session_id}: {str(e)}")
            raise
