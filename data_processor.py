import pandas as pd
import numpy as np
import json
import logging
from datetime import datetime
from sqlalchemy import text
from models import ProcessingSession, EmailRecord, ProcessingError, Rule, WhitelistDomain, AttachmentKeyword
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

            risk_keywords = self._risk_keywords_cache
            exclusion_keywords = self._exclusion_keywords_cache

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
        """Apply complete processing workflow"""
        try:
            logger.info(f"Starting processing workflow for session {session_id}")

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