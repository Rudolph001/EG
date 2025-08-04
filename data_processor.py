
import pandas as pd
import numpy as np
import json
import logging
import os
import time
from datetime import datetime
from sqlalchemy import text
from models import ProcessingSession, EmailRecord, ProcessingError, Rule, WhitelistDomain, AttachmentKeyword
from app import db
from performance_config import config
from workflow_manager import WorkflowManager
import re

logger = logging.getLogger(__name__)

class DataProcessor:
    """Main data processing engine for CSV files with custom wordlist matching"""
    
    def __init__(self):
        self.chunk_size = config.chunk_size
        self.batch_commit_size = config.batch_commit_size
        self.workflow_manager = WorkflowManager()
        logger.info(f"DataProcessor initialized with config: {config.__dict__}")
    
    def process_csv(self, session_id, file_path):
        """Process CSV file with comprehensive 8-stage workflow and improved error handling"""
        session = None
        try:
            logger.info(f"Starting CSV processing for session {session_id}")
            
            # Initialize workflow with database connection validation
            session = self._get_session_with_retry(session_id)
            if not session:
                raise Exception(f"Session {session_id} not found")
            
            # Check if processing can be resumed
            if session.status == 'processing' and session.processed_records > 0:
                logger.info(f"Resuming processing for session {session_id} from record {session.processed_records}")
                return self._resume_processing(session_id, file_path)
            
            session.status = 'processing'
            session.data_path = file_path
            session.error_message = None
            self._commit_with_retry()
            
            # Initialize 8-stage workflow
            self.workflow_manager.initialize_workflow(session_id)
            
            # Stage 1: Data Ingestion (0-5%)
            self.workflow_manager.start_stage(session_id, 1)
            
            # Count total records first with validation
            total_records = self._count_csv_records_with_validation(file_path)
            session.total_records = total_records
            self._commit_with_retry()
            
            logger.info(f"Processing {total_records} records in chunks of {self.chunk_size}")
            
            processed_count = 0
            current_chunk = 0
            
            # Process file in chunks with enhanced error handling
            try:
                for chunk_df in pd.read_csv(file_path, chunksize=self.chunk_size):
                    current_chunk += 1
                    
                    # Process chunk with retry mechanism
                    chunk_processed = self._process_chunk_with_retry(session_id, chunk_df, processed_count, current_chunk)
                    processed_count += chunk_processed
                    
                    # Update session with retry
                    session = self._get_session_with_retry(session_id)
                    session.current_chunk = current_chunk
                    session.total_chunks = (total_records // self.chunk_size) + 1
                    session.processed_records = processed_count
                    
                    # Update progress within Data Ingestion stage (0-5%)
                    progress = min(100, (processed_count / total_records) * 100) if total_records > 0 else 100
                    self.workflow_manager.update_stage_progress(session_id, 1, progress)
                    
                    self._commit_with_retry()
                    
                    logger.info(f"Processed chunk {current_chunk}: {processed_count}/{total_records} records")
                    
                    # Yield control to prevent blocking
                    if current_chunk % 5 == 0:
                        import time
                        time.sleep(0.1)
                        
            except Exception as chunk_error:
                logger.error(f"Error processing chunks: {str(chunk_error)}")
                raise Exception(f"Data ingestion failed at chunk {current_chunk}: {str(chunk_error)}")
            
            # Complete Data Ingestion
            self.workflow_manager.complete_stage(session_id, 1)
            logger.info(f"Data Ingestion completed: {processed_count} records processed")
            
            # Apply remaining 7-stage processing workflow
            self._apply_8_stage_workflow(session_id)
            
            # Final completion
            session = self._get_session_with_retry(session_id)
            session.processed_records = processed_count
            session.status = 'completed'
            self._commit_with_retry()
            
            logger.info(f"8-stage CSV processing completed for session {session_id}: {processed_count} records")
            
        except Exception as e:
            logger.error(f"Error processing CSV for session {session_id}: {str(e)}")
            try:
                if not session:
                    session = self._get_session_with_retry(session_id)
                
                if session:
                    # Mark current stage as error with detailed message
                    if hasattr(self, 'workflow_manager') and session.current_stage > 0:
                        error_msg = f"Stage {session.current_stage} failed: {str(e)}"
                        self.workflow_manager.error_stage(session_id, session.current_stage, error_msg)
                    else:
                        session.status = 'error'
                        session.error_message = f"Processing failed: {str(e)}"
                    self._commit_with_retry()
            except Exception as error_handling_exception:
                logger.error(f"Failed to handle error properly: {str(error_handling_exception)}")
            raise
    
    def _get_session_with_retry(self, session_id, max_retries=3):
        """Get session with database retry mechanism"""
        for attempt in range(max_retries):
            try:
                session = ProcessingSession.query.get(session_id)
                return session
            except Exception as e:
                logger.warning(f"Database connection attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)
                    continue
                else:
                    raise Exception(f"Failed to connect to database after {max_retries} attempts")
    
    def _commit_with_retry(self, max_retries=3):
        """Commit database changes with retry mechanism"""
        for attempt in range(max_retries):
            try:
                db.session.commit()
                return True
            except Exception as e:
                logger.warning(f"Database commit attempt {attempt + 1} failed: {str(e)}")
                db.session.rollback()
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)
                    continue
                else:
                    raise Exception(f"Failed to commit to database after {max_retries} attempts")
    
    def _count_csv_records_with_validation(self, file_path):
        """Count total records in CSV file with validation"""
        try:
            # Validate file exists and is readable
            if not os.path.exists(file_path):
                raise Exception(f"File not found: {file_path}")
            
            # Count records efficiently
            with open(file_path, 'r', encoding='utf-8') as f:
                return sum(1 for line in f) - 1  # Subtract header
                
        except Exception as e:
            logger.warning(f"Could not count CSV records efficiently: {e}")
            try:
                # Fallback to pandas with validation
                df = pd.read_csv(file_path, nrows=0)  # Just read header first
                df = pd.read_csv(file_path)  # Then read full file
                return len(df)
            except Exception as pandas_error:
                raise Exception(f"Failed to read CSV file: {str(pandas_error)}")
    
    def _process_chunk_with_retry(self, session_id, chunk_df, start_index, chunk_number, max_retries=3):
        """Process a chunk with retry mechanism"""
        for attempt in range(max_retries):
            try:
                return self._process_chunk(session_id, chunk_df, start_index)
            except Exception as e:
                logger.warning(f"Chunk {chunk_number} processing attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)
                    db.session.rollback()  # Rollback failed transaction
                    continue
                else:
                    raise Exception(f"Failed to process chunk {chunk_number} after {max_retries} attempts: {str(e)}")
    
    def _resume_processing(self, session_id, file_path):
        """Resume processing from where it left off"""
        try:
            logger.info(f"Attempting to resume processing for session {session_id}")
            
            session = self._get_session_with_retry(session_id)
            if not session:
                raise Exception(f"Session {session_id} not found for resume")
            
            # Get current processing state
            processed_records = session.processed_records or 0
            total_records = session.total_records or self._count_csv_records_with_validation(file_path)
            
            # Check if data ingestion is complete
            if processed_records >= total_records:
                logger.info(f"Data ingestion already complete, proceeding to workflow stages")
                self.workflow_manager.complete_stage(session_id, 1)
                self._apply_8_stage_workflow(session_id)
                return
            
            # Resume data ingestion from current position
            current_chunk = session.current_chunk or 0
            
            logger.info(f"Resuming from record {processed_records}, chunk {current_chunk}")
            
            # Skip to the correct position in file
            chunk_iterator = pd.read_csv(file_path, chunksize=self.chunk_size)
            
            # Skip already processed chunks
            for i in range(current_chunk):
                try:
                    next(chunk_iterator)
                except StopIteration:
                    break
            
            # Continue processing from current position
            for chunk_df in chunk_iterator:
                current_chunk += 1
                
                chunk_processed = self._process_chunk_with_retry(session_id, chunk_df, processed_records, current_chunk)
                processed_records += chunk_processed
                
                # Update session
                session = self._get_session_with_retry(session_id)
                session.current_chunk = current_chunk
                session.processed_records = processed_records
                
                # Update progress
                progress = min(100, (processed_records / total_records) * 100) if total_records > 0 else 100
                self.workflow_manager.update_stage_progress(session_id, 1, progress)
                
                self._commit_with_retry()
                
                logger.info(f"Resumed chunk {current_chunk}: {processed_records}/{total_records} records")
            
            # Complete data ingestion and continue with workflow
            self.workflow_manager.complete_stage(session_id, 1)
            self._apply_8_stage_workflow(session_id)
            
            logger.info(f"Resume processing completed for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error resuming processing: {str(e)}")
            raise
    
    def _count_csv_records(self, file_path):
        """Count total records in CSV file (legacy method)"""
        return self._count_csv_records_with_validation(file_path)
    
    def _process_chunk(self, session_id, chunk_df, start_index):
        """Process a chunk of data with custom wordlist matching"""
        try:
            records_to_add = []
            
            for idx, row in chunk_df.iterrows():
                try:
                    # Create email record with custom wordlist analysis
                    record = self._create_email_record(session_id, row, start_index + idx)
                    records_to_add.append(record)
                    
                    # Batch commit for performance
                    if len(records_to_add) >= self.batch_commit_size:
                        db.session.add_all(records_to_add)
                        db.session.commit()
                        records_to_add = []
                        
                except Exception as e:
                    logger.warning(f"Error processing record at index {idx}: {str(e)}")
                    self._log_processing_error(session_id, 'record_processing', str(e), row.to_dict())
                    continue
            
            # Commit remaining records
            if records_to_add:
                db.session.add_all(records_to_add)
                db.session.commit()
            
            return len(chunk_df)
            
        except Exception as e:
            logger.error(f"Error processing chunk: {str(e)}")
            db.session.rollback()
            raise
    
    def _create_email_record(self, session_id, row, record_index):
        """Create email record with custom wordlist analysis"""
        # Extract basic fields
        record_data = {
            'session_id': session_id,
            'record_id': str(row.get('Record ID', f'record_{record_index}')),
            'sender': str(row.get('Sender', '')),
            'subject': str(row.get('Subject', '')),
            'recipients': str(row.get('Recipients', '')),
            'recipients_email_domain': str(row.get('Recipients Email Domain', '')),
            'time': self._parse_datetime(row.get('Time')),
            'attachments': str(row.get('Attachments', '')),
            'leaver': str(row.get('Leaver', '')),
            'termination_date': self._parse_datetime(row.get('Termination Date')),
            'bunit': str(row.get('BUnit', '')),
            'department': str(row.get('Department', '')),
            'status': str(row.get('Status', '')),
            'user_response': str(row.get('User Response', '')),
            'final_outcome': str(row.get('Final Outcome', '')),
            'justification': str(row.get('Justification', '')),
            'policy_name': str(row.get('Policy Name', 'Standard'))
        }
        
        # Apply custom wordlist matching
        self._apply_custom_wordlist_analysis(record_data)
        
        return EmailRecord(**record_data)
    
    def _apply_custom_wordlist_analysis(self, record_data):
        """Apply custom wordlist matching for risk and exclusion analysis"""
        try:
            # Get active wordlists from database
            risk_keywords = AttachmentKeyword.query.filter_by(
                is_active=True,
                keyword_type='risk'
            ).all()
            
            exclusion_keywords = AttachmentKeyword.query.filter_by(
                is_active=True,
                keyword_type='exclusion'
            ).all()
            
            # Initialize wordlist fields
            subject_matches = []
            attachment_matches = []
            exclusion_matches = []
            
            subject_text = (record_data.get('subject', '') or '').lower()
            attachment_text = (record_data.get('attachments', '') or '').lower()
            
            # Check risk keywords
            for keyword_obj in risk_keywords:
                keyword = keyword_obj.keyword.lower()
                applies_to = keyword_obj.applies_to or 'both'
                
                # Check subject
                if applies_to in ['subject', 'both'] and keyword in subject_text:
                    subject_matches.append({
                        'keyword': keyword_obj.keyword,
                        'category': keyword_obj.category,
                        'risk_score': keyword_obj.risk_score
                    })
                
                # Check attachments
                if applies_to in ['attachment', 'both'] and keyword in attachment_text:
                    attachment_matches.append({
                        'keyword': keyword_obj.keyword,
                        'category': keyword_obj.category,
                        'risk_score': keyword_obj.risk_score
                    })
            
            # Check exclusion keywords
            for keyword_obj in exclusion_keywords:
                keyword = keyword_obj.keyword.lower()
                applies_to = keyword_obj.applies_to or 'both'
                
                found_in_subject = applies_to in ['subject', 'both'] and keyword in subject_text
                found_in_attachment = applies_to in ['attachment', 'both'] and keyword in attachment_text
                
                if found_in_subject or found_in_attachment:
                    exclusion_matches.append({
                        'keyword': keyword_obj.keyword,
                        'found_in': 'subject' if found_in_subject else 'attachment'
                    })
            
            # Store results in record
            record_data['wordlist_subject'] = json.dumps(subject_matches) if subject_matches else None
            record_data['wordlist_attachment'] = json.dumps(attachment_matches) if attachment_matches else None
            
            # Set exclusion flag if any exclusion keywords found
            if exclusion_matches:
                record_data['excluded_by_rule'] = f"Exclusion wordlist: {', '.join([m['keyword'] for m in exclusion_matches])}"
            
        except Exception as e:
            logger.warning(f"Error in custom wordlist analysis: {str(e)}")
            # Set empty values if analysis fails
            record_data['wordlist_subject'] = None
            record_data['wordlist_attachment'] = None
    
    def _parse_datetime(self, date_value):
        """Parse datetime from various formats"""
        if pd.isna(date_value) or date_value is None or str(date_value).strip() == '':
            return None
        
        try:
            if isinstance(date_value, str):
                # Try common formats
                formats = [
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d',
                    '%m/%d/%Y %H:%M:%S',
                    '%m/%d/%Y',
                    '%d/%m/%Y %H:%M:%S',
                    '%d/%m/%Y'
                ]
                
                for fmt in formats:
                    try:
                        return datetime.strptime(date_value.strip(), fmt)
                    except ValueError:
                        continue
                
                # If all formats fail, return None
                logger.warning(f"Could not parse date: {date_value}")
                return None
            else:
                # Assume it's already a datetime object
                return date_value
        except Exception as e:
            logger.warning(f"Error parsing datetime {date_value}: {str(e)}")
            return None
    
    def _apply_8_stage_workflow(self, session_id):
        """Apply the comprehensive 8-stage processing workflow"""
        try:
            logger.info(f"Starting 8-stage workflow for session {session_id}")
            
            # Stage 2: Exclusion Rules (5-20%)
            self.workflow_manager.start_stage(session_id, 2)
            self._apply_exclusion_rules(session_id)
            self.workflow_manager.complete_stage(session_id, 2)
            
            # Stage 3: Whitelist Filtering (20-35%)
            self.workflow_manager.start_stage(session_id, 3)
            self._apply_whitelist_filtering(session_id)
            self.workflow_manager.complete_stage(session_id, 3)
            
            # Stage 4: Security Rules (35-50%)
            self.workflow_manager.start_stage(session_id, 4)
            self._apply_security_rules(session_id)
            self.workflow_manager.complete_stage(session_id, 4)
            
            # Stage 5: Wordlist Analysis (50-65%)
            self.workflow_manager.start_stage(session_id, 5)
            self._apply_wordlist_analysis(session_id)
            self.workflow_manager.complete_stage(session_id, 5)
            
            # Stage 6: ML Analysis (65-80%)
            self.workflow_manager.start_stage(session_id, 6)
            self._apply_ml_analysis(session_id)
            self.workflow_manager.complete_stage(session_id, 6)
            
            # Stage 7: Case Generation (80-90%)
            self.workflow_manager.start_stage(session_id, 7)
            self._generate_cases(session_id)
            self.workflow_manager.complete_stage(session_id, 7)
            
            # Stage 8: Final Validation (90-100%)
            self.workflow_manager.start_stage(session_id, 8)
            self._final_validation(session_id)
            self.workflow_manager.complete_stage(session_id, 8)
            
            logger.info(f"8-stage workflow completed for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error in 8-stage workflow for session {session_id}: {str(e)}")
            session = ProcessingSession.query.get(session_id)
            if session and session.current_stage > 0:
                self.workflow_manager.error_stage(session_id, session.current_stage, str(e))
            raise
    
    def _apply_exclusion_rules(self, session_id):
        """Stage 2: Apply exclusion rules"""
        try:
            from rule_engine import RuleEngine
            rule_engine = RuleEngine()
            excluded_count = rule_engine.apply_exclusion_rules(session_id)
            logger.info(f"Exclusion rules applied: {excluded_count} records excluded")
            self._mark_workflow_step_completed(session_id, 'exclusion_applied')
        except Exception as e:
            logger.error(f"Error in exclusion rules stage: {str(e)}")
            raise
    
    def _apply_whitelist_filtering(self, session_id):
        """Stage 3: Apply whitelist filtering"""
        try:
            from domain_manager import DomainManager
            domain_manager = DomainManager()
            whitelisted_count = domain_manager.apply_whitelist(session_id)
            logger.info(f"Domain whitelist applied: {whitelisted_count} records whitelisted")
            self._mark_workflow_step_completed(session_id, 'whitelist_applied')
        except Exception as e:
            logger.error(f"Error in whitelist filtering stage: {str(e)}")
            raise
    
    def _apply_security_rules(self, session_id):
        """Stage 4: Apply security rules"""
        try:
            from rule_engine import RuleEngine
            rule_engine = RuleEngine()
            flagged_count = rule_engine.apply_security_rules(session_id)
            logger.info(f"Security rules applied: {flagged_count} records flagged")
            self._mark_workflow_step_completed(session_id, 'rules_applied')
        except Exception as e:
            logger.error(f"Error in security rules stage: {str(e)}")
            raise
    
    def _apply_wordlist_analysis(self, session_id):
        """Stage 5: Apply wordlist analysis (already done in record creation)"""
        try:
            # Wordlist analysis is already done during record creation
            # This stage validates and finalizes wordlist results
            records = EmailRecord.query.filter_by(session_id=session_id).all()
            wordlist_count = sum(1 for r in records if r.wordlist_subject or r.wordlist_attachment)
            logger.info(f"Wordlist analysis validated: {wordlist_count} records with wordlist matches")
        except Exception as e:
            logger.error(f"Error in wordlist analysis stage: {str(e)}")
            raise
    
    def _apply_ml_analysis(self, session_id):
        """Stage 6: Apply ML analysis"""
        try:
            from ml_engine import MLEngine
            ml_engine = MLEngine()
            analyzed_count = ml_engine.analyze_session(session_id)
            logger.info(f"ML analysis applied: {analyzed_count} records analyzed")
            self._mark_workflow_step_completed(session_id, 'ml_applied')
        except Exception as e:
            logger.error(f"Error in ML analysis stage: {str(e)}")
            raise
    
    def _generate_cases(self, session_id):
        """Stage 7: Generate security cases"""
        try:
            # Cases are automatically generated based on risk levels
            records = EmailRecord.query.filter_by(session_id=session_id).all()
            case_count = sum(1 for r in records if r.risk_level and r.risk_level != 'Low')
            logger.info(f"Security cases generated: {case_count} cases created")
        except Exception as e:
            logger.error(f"Error in case generation stage: {str(e)}")
            raise
    
    def _final_validation(self, session_id):
        """Stage 8: Final validation and cleanup"""
        try:
            session = ProcessingSession.query.get(session_id)
            if not session:
                raise Exception(f"Session {session_id} not found")
            
            # Validate processing results
            total_records = EmailRecord.query.filter_by(session_id=session_id).count()
            analyzed_records = EmailRecord.query.filter_by(session_id=session_id).filter(
                EmailRecord.ml_risk_score.isnot(None)
            ).count()
            
            # Update final statistics
            session.processing_stats = {
                'total_records': total_records,
                'analyzed_records': analyzed_records,
                'analysis_rate': (analyzed_records / total_records * 100) if total_records > 0 else 0,
                'workflow_completed': True
            }
            
            db.session.commit()
            logger.info(f"Final validation completed: {total_records} total, {analyzed_records} analyzed")
            
        except Exception as e:
            logger.error(f"Error in final validation stage: {str(e)}")
            raise

    def _apply_processing_workflow(self, session_id):
        """Apply complete processing workflow (Legacy method)"""
        try:
            logger.info(f"Starting legacy processing workflow for session {session_id}")
            
            # Import required engines
            from rule_engine import RuleEngine
            from domain_manager import DomainManager
            from ml_engine import MLEngine
            
            rule_engine = RuleEngine()
            domain_manager = DomainManager()
            ml_engine = MLEngine()
            
            # Step 1: Apply exclusion rules
            if not self._is_workflow_step_completed(session_id, 'exclusion_applied'):
                excluded_count = rule_engine.apply_exclusion_rules(session_id)
                logger.info(f"Exclusion rules applied: {excluded_count} records excluded")
                self._mark_workflow_step_completed(session_id, 'exclusion_applied')
            
            # Step 2: Apply domain whitelist
            if not self._is_workflow_step_completed(session_id, 'whitelist_applied'):
                whitelisted_count = domain_manager.apply_whitelist(session_id)
                logger.info(f"Domain whitelist applied: {whitelisted_count} records whitelisted")
                self._mark_workflow_step_completed(session_id, 'whitelist_applied')
            
            # Step 3: Apply security rules
            if not self._is_workflow_step_completed(session_id, 'rules_applied'):
                flagged_count = rule_engine.apply_security_rules(session_id)
                logger.info(f"Security rules applied: {flagged_count} records flagged")
                self._mark_workflow_step_completed(session_id, 'rules_applied')
            
            # Step 4: Apply ML analysis
            if not self._is_workflow_step_completed(session_id, 'ml_applied'):
                analyzed_count = ml_engine.analyze_session(session_id)
                logger.info(f"ML analysis applied: {analyzed_count} records analyzed")
                self._mark_workflow_step_completed(session_id, 'ml_applied')
            
        except Exception as e:
            logger.error(f"Error in processing workflow for session {session_id}: {str(e)}")
            raise
    
    def _is_workflow_step_completed(self, session_id, step_name):
        """Check if a workflow step has been completed"""
        session = ProcessingSession.query.get(session_id)
        return getattr(session, step_name, False) if session else False
    
    def _mark_workflow_step_completed(self, session_id, step_name):
        """Mark a workflow step as completed"""
        session = ProcessingSession.query.get(session_id)
        if session:
            setattr(session, step_name, True)
            db.session.commit()
    
    def _log_processing_error(self, session_id, error_type, error_message, record_data=None):
        """Log processing error to database"""
        try:
            error_record = ProcessingError(
                session_id=session_id,
                error_type=error_type,
                error_message=error_message,
                record_data=record_data
            )
            db.session.add(error_record)
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed to log processing error: {str(e)}")
    
    def get_processing_summary(self, session_id):
        """Get processing summary for a session"""
        try:
            session = ProcessingSession.query.get(session_id)
            if not session:
                return None
            
            total_records = EmailRecord.query.filter_by(session_id=session_id).count()
            excluded_records = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.excluded_by_rule.isnot(None)
            ).count()
            whitelisted_records = EmailRecord.query.filter_by(
                session_id=session_id,
                whitelisted=True
            ).count()
            analyzed_records = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.ml_risk_score.isnot(None)
            ).count()
            
            return {
                'session_id': session_id,
                'filename': session.filename,
                'status': session.status,
                'total_records': total_records,
                'excluded_records': excluded_records,
                'whitelisted_records': whitelisted_records,
                'analyzed_records': analyzed_records,
                'processing_started': session.upload_time,
                'workflow_status': {
                    'exclusion_applied': session.exclusion_applied,
                    'whitelist_applied': session.whitelist_applied,
                    'rules_applied': session.rules_applied,
                    'ml_applied': session.ml_applied
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting processing summary for session {session_id}: {str(e)}")
            return None
