import pandas as pd
import numpy as np
import json
import logging
from datetime import datetime
from sqlalchemy import text
from models import ProcessingSession, EmailRecord, AttachmentKeyword, ProcessingError, Rule, WhitelistDomain
from app import db
from performance_config import config
import re

logger = logging.getLogger(__name__)

class DataProcessor:
    """Main data processing engine for CSV files with custom wordlist matching"""

    def __init__(self):
        self.chunk_size = config.chunk_size
        self.batch_commit_size = config.batch_commit_size
        # Cache keywords globally to avoid repeated DB queries
        self._risk_keywords_cache = None
        self._exclusion_keywords_cache = None
        self._keywords_cached = False
        logger.info(f"DataProcessor initialized with config: {config.get_config_summary()}")

    def process_csv(self, session_id, file_path):
        """Process CSV file with comprehensive analysis pipeline"""
        try:
            logger.info(f"Starting CSV processing for session {session_id}")

            # Update session status
            from models import ProcessingSession
            session = ProcessingSession.query.get(session_id)
            if not session:
                raise Exception(f"Session {session_id} not found")

            session.status = 'processing'
            session.data_path = file_path
            db.session.commit()

            # Count total records first
            total_records = self._count_csv_records(file_path)
            session.total_records = total_records
            db.session.commit()

            logger.info(f"Processing {total_records} records in chunks of {self.chunk_size}")

            processed_count = 0
            current_chunk = 0

            # Process file in chunks
            for chunk_df in pd.read_csv(file_path, chunksize=self.chunk_size):
                current_chunk += 1
                session.current_chunk = current_chunk
                session.total_chunks = (total_records // self.chunk_size) + 1

                chunk_processed = self._process_chunk(session_id, chunk_df, processed_count)
                processed_count += chunk_processed

                # Update progress
                session.processed_records = processed_count
                db.session.commit()

                logger.info(f"Processed chunk {current_chunk}: {processed_count}/{total_records} records")

            # Apply processing workflow
            self._apply_processing_workflow(session_id)

            # Mark session as completed
            session.status = 'completed'
            session.processed_records = processed_count
            db.session.commit()

            logger.info(f"CSV processing completed for session {session_id}: {processed_count} records")

        except Exception as e:
            logger.error(f"Error processing CSV for session {session_id}: {str(e)}")
            from models import ProcessingSession
            session = ProcessingSession.query.get(session_id)
            if session:
                session.status = 'error'
                session.error_message = str(e)
                db.session.commit()
            raise

    def _count_csv_records(self, file_path):
        """Count total records in CSV file"""
        try:
            return sum(1 for line in open(file_path, 'r', encoding='utf-8')) - 1  # Subtract header
        except Exception as e:
            logger.warning(f"Could not count CSV records efficiently: {e}")
            # Fallback to pandas
            df = pd.read_csv(file_path)
            return len(df)

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
            'sender': str(row.get('sender', '')),
            'subject': str(row.get('subject', '')),
            'recipients': str(row.get('recipients', '')),
            'recipients_email_domain': str(row.get('recipients_email_domain', '')),
            'time': self._parse_datetime(row.get('_time')),
            'attachments': str(row.get('attachments', '')),
            'leaver': str(row.get('leaver', '')),
            'termination_date': self._parse_datetime(row.get('termination_date')),
            'bunit': str(row.get('bunit', '')),
            'department': str(row.get('department', '')),
            'status': str(row.get('status', '')),
            'user_response': str(row.get('user_response', '')),
            'final_outcome': str(row.get('final_outcome', '')),
            'justification': str(row.get('justification', '')),
            'policy_name': str(row.get('Policy Name', 'Standard'))
        }

        # Apply custom wordlist matching
        self._apply_custom_wordlist_analysis(record_data)

        return EmailRecord(**record_data)

    def _apply_custom_wordlist_analysis(self, record_data):
        """Apply custom wordlist matching for risk and exclusion analysis"""
        try:
            # Use cached keywords to avoid repeated database queries
            if not self._keywords_cached:
                self._risk_keywords_cache = AttachmentKeyword.query.filter_by(
                    is_active=True,
                    keyword_type='risk'
                ).all()

                self._exclusion_keywords_cache = AttachmentKeyword.query.filter_by(
                    is_active=True,
                    keyword_type='exclusion'
                ).all()

                self._keywords_cached = True
                logger.info(f"Cached {len(self._risk_keywords_cache)} risk keywords and {len(self._exclusion_keywords_cache)} exclusion keywords")

            # Ensure keywords are never None to prevent iteration errors
            risk_keywords = self._risk_keywords_cache or []
            exclusion_keywords = self._exclusion_keywords_cache or []

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
            # Note: exclusion_matches is stored in excluded_by_rule field, not as separate field

            # Set exclusion flag ONLY if exclusion keywords found AND no risk keywords found
            if exclusion_matches and not (subject_matches or attachment_matches):
                record_data['excluded_by_rule'] = f"Exclusion wordlist: {', '.join([m['keyword'] for m in exclusion_matches])}"
            elif exclusion_matches and (subject_matches or attachment_matches):
                # Log when exclusion is overridden by risk keywords
                logger.info(f"Email with exclusion keywords NOT excluded due to risk keywords present. "
                          f"Exclusion: {[m['keyword'] for m in exclusion_matches]}, "
                          f"Risk: {[m['keyword'] for m in subject_matches + attachment_matches]}")

        except Exception as e:
            logger.warning(f"Error in custom wordlist analysis: {str(e)}")
            # Set empty values if analysis fails
            record_data['wordlist_subject'] = None
            record_data['wordlist_attachment'] = None
            # Note: exclusion_matches is stored in excluded_by_rule field, not as separate field

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

    def _apply_processing_workflow(self, session_id):
        """Apply complete processing workflow in strict sequential order"""
        try:
            logger.info(f"Starting sequential processing workflow for session {session_id}")

            # Import required engines and models
            from models import ProcessingSession
            from rule_engine import RuleEngine
            from domain_manager import DomainManager
            from ml_engine import MLEngine

            rule_engine = RuleEngine()
            domain_manager = DomainManager()
            ml_engine = MLEngine()

            # Get session for status updates
            session = ProcessingSession.query.get(session_id)
            if not session:
                raise Exception(f"Session {session_id} not found")

            # Step 1: Apply exclusion rules - MUST complete before Step 2
            try:
                if not self._is_workflow_step_completed(session_id, 'exclusion_applied'):
                    logger.info(f"=== STEP 1: EXCLUSION RULES ===")
                    logger.info(f"Starting exclusion rules processing for session {session_id}")
                    
                    # Update session to show current step
                    session.status = 'processing_exclusion'
                    db.session.commit()
                    
                    excluded_count = rule_engine.apply_exclusion_rules(session_id)
                    logger.info(f"Exclusion rules completed: {excluded_count} records excluded")
                    
                    # Mark step as completed and commit immediately
                    self._mark_workflow_step_completed(session_id, 'exclusion_applied')
                    db.session.commit()
                    
                    logger.info(f"✓ STEP 1 COMPLETED: Exclusion Rules ({excluded_count} records)")
                else:
                    logger.info(f"✓ STEP 1 ALREADY COMPLETED: Exclusion Rules")
            except Exception as e:
                logger.error(f"✗ STEP 1 FAILED: {str(e)}")
                session.status = 'error'
                session.error_message = f"Step 1 failed: {str(e)}"
                db.session.commit()
                raise

            # Wait for Step 1 completion confirmation
            db.session.refresh(session)
            if not session.exclusion_applied:
                raise Exception("Step 1 (Exclusion Rules) did not complete properly")

            # Step 2: Apply domain whitelist - ONLY after Step 1 is complete
            try:
                if not self._is_workflow_step_completed(session_id, 'whitelist_applied'):
                    logger.info(f"=== STEP 2: DOMAIN WHITELIST ===")
                    logger.info(f"Starting domain whitelist processing for session {session_id}")
                    
                    # Update session to show current step
                    session.status = 'processing_whitelist'
                    db.session.commit()
                    
                    whitelisted_count = domain_manager.apply_whitelist(session_id)
                    logger.info(f"Domain whitelist completed: {whitelisted_count} records whitelisted")
                    
                    # Mark step as completed and commit immediately
                    self._mark_workflow_step_completed(session_id, 'whitelist_applied')
                    db.session.commit()
                    
                    logger.info(f"✓ STEP 2 COMPLETED: Domain Whitelist ({whitelisted_count} records)")
                else:
                    logger.info(f"✓ STEP 2 ALREADY COMPLETED: Domain Whitelist")
            except Exception as e:
                logger.error(f"✗ STEP 2 FAILED: {str(e)}")
                session.status = 'error'
                session.error_message = f"Step 2 failed: {str(e)}"
                db.session.commit()
                raise

            # Wait for Step 2 completion confirmation
            db.session.refresh(session)
            if not session.whitelist_applied:
                raise Exception("Step 2 (Domain Whitelist) did not complete properly")

            # Step 3: Apply security rules - ONLY after Step 2 is complete
            try:
                if not self._is_workflow_step_completed(session_id, 'rules_applied'):
                    logger.info(f"=== STEP 3: SECURITY RULES ===")
                    logger.info(f"Starting security rules processing for session {session_id}")
                    
                    # Update session to show current step
                    session.status = 'processing_security'
                    db.session.commit()
                    
                    flagged_count = rule_engine.apply_security_rules(session_id)
                    logger.info(f"Security rules completed: {flagged_count} records flagged")
                    
                    # Mark step as completed and commit immediately
                    self._mark_workflow_step_completed(session_id, 'rules_applied')
                    db.session.commit()
                    
                    logger.info(f"✓ STEP 3 COMPLETED: Security Rules ({flagged_count} records)")
                else:
                    logger.info(f"✓ STEP 3 ALREADY COMPLETED: Security Rules")
            except Exception as e:
                logger.error(f"✗ STEP 3 FAILED: {str(e)}")
                session.status = 'error'
                session.error_message = f"Step 3 failed: {str(e)}"
                db.session.commit()
                raise

            # Wait for Step 3 completion confirmation
            db.session.refresh(session)
            if not session.rules_applied:
                raise Exception("Step 3 (Security Rules) did not complete properly")

            # Step 4: Apply ML analysis - ONLY after Step 3 is complete
            try:
                if not self._is_workflow_step_completed(session_id, 'ml_applied'):
                    logger.info(f"=== STEP 4: ML ANALYSIS ===")
                    logger.info(f"Starting ML analysis processing for session {session_id}")
                    
                    # Update session to show current step
                    session.status = 'processing_ml'
                    db.session.commit()
                    
                    analyzed_count = ml_engine.analyze_session(session_id)
                    logger.info(f"ML analysis completed: {analyzed_count} records analyzed")
                    
                    # Mark step as completed and commit immediately
                    self._mark_workflow_step_completed(session_id, 'ml_applied')
                    db.session.commit()
                    
                    logger.info(f"✓ STEP 4 COMPLETED: ML Analysis ({analyzed_count} records)")
                else:
                    logger.info(f"✓ STEP 4 ALREADY COMPLETED: ML Analysis")
            except Exception as e:
                logger.error(f"✗ STEP 4 FAILED: {str(e)}")
                session.status = 'error'
                session.error_message = f"Step 4 failed: {str(e)}"
                db.session.commit()
                raise

            # Final verification - all steps must be complete
            db.session.refresh(session)
            if not (session.exclusion_applied and session.whitelist_applied and 
                   session.rules_applied and session.ml_applied):
                raise Exception("Workflow verification failed - not all steps completed")

            logger.info(f"✓ ALL WORKFLOW STEPS COMPLETED SUCCESSFULLY for session {session_id}")
            session.status = 'processing'  # Reset to processing for final completion
            db.session.commit()

        except Exception as e:
            logger.error(f"Error in sequential processing workflow for session {session_id}: {str(e)}")
            session = ProcessingSession.query.get(session_id)
            if session:
                session.status = 'error'
                session.error_message = str(e)
                db.session.commit()
            raise

    def _is_workflow_step_completed(self, session_id, step_name):
        """Check if a workflow step has been completed with proper error handling"""
        try:
            from models import ProcessingSession
            # Use fresh session query to avoid stale data
            session = db.session.get(ProcessingSession, session_id)
            return getattr(session, step_name, False) if session else False
        except Exception as e:
            logger.error(f"Error checking workflow step '{step_name}': {str(e)}")
            # Assume not completed if we can't check
            return False

    def _mark_workflow_step_completed(self, session_id, step_name):
        """Mark a workflow step as completed with proper error handling"""
        try:
            from models import ProcessingSession
            # Refresh session to avoid stale object issues
            session = db.session.get(ProcessingSession, session_id)
            if session:
                setattr(session, step_name, True)
                db.session.commit()
                logger.debug(f"Marked workflow step '{step_name}' as completed for session {session_id}")
        except Exception as e:
            logger.error(f"Error marking workflow step '{step_name}' as completed: {str(e)}")
            db.session.rollback()
            # Try again with fresh session
            try:
                session = db.session.get(ProcessingSession, session_id)
                if session:
                    setattr(session, step_name, True)
                    db.session.commit()
            except Exception as retry_error:
                logger.error(f"Retry failed for workflow step '{step_name}': {str(retry_error)}")
                db.session.rollback()

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
            from models import ProcessingSession
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