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
import threading
import time

logger = logging.getLogger(__name__)

class DataProcessor:
    """Enhanced CSV processor with improved workflow handling"""

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
        """Main CSV processing workflow with improved error handling"""
        try:
            logger.info(f"Starting enhanced CSV processing for session {session_id}")

            # Get session and validate
            session = ProcessingSession.query.get(session_id)
            if not session:
                logger.error(f"Session {session_id} not found")
                return

            # Reset session state for fresh processing
            self._reset_session_state(session)

            # Step 1: Validate CSV structure
            column_mapping = self._validate_csv_structure(file_path)

            # Step 2: Count total records
            total_records = self._count_csv_rows(file_path)
            session.total_records = total_records
            db.session.commit()

            if total_records == 0:
                logger.warning(f"No records found in CSV file for session {session_id}")
                session.status = 'completed'
                db.session.commit()
                return

            # Step 3: Process CSV data in chunks
            processed_count = self._process_csv_chunks(session_id, file_path, column_mapping, total_records)

            # Step 4: Apply workflow with enhanced error handling
            self._apply_enhanced_workflow(session_id)

            # Step 5: Mark as completed
            session.status = 'completed'
            session.processed_records = processed_count
            session.completed_at = datetime.utcnow()
            db.session.commit()

            logger.info(f"Enhanced CSV processing completed for session {session_id}: {processed_count} records")

        except Exception as e:
            logger.error(f"Critical error in CSV processing for session {session_id}: {str(e)}")
            self._handle_processing_error(session_id, str(e))

    def _reset_session_state(self, session):
        """Reset session state for fresh processing"""
        session.status = 'processing'
        session.processed_records = 0
        session.current_chunk = 0
        session.total_chunks = 0
        session.exclusion_applied = False
        session.whitelist_applied = False
        session.rules_applied = False
        session.ml_applied = False
        session.error_message = None
        db.session.commit()
        logger.info(f"Session {session.id} state reset for fresh processing")

    def _validate_csv_structure(self, file_path):
        """Enhanced CSV structure validation"""
        try:
            sample_df = pd.read_csv(file_path, nrows=10)
            actual_columns = [col.lower().strip() for col in sample_df.columns]

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

            if missing_columns:
                logger.warning(f"Missing columns: {missing_columns}")

            logger.info(f"CSV validation successful. Mapped {len(column_mapping)} columns")
            return column_mapping

        except Exception as e:
            logger.error(f"CSV validation failed: {str(e)}")
            raise ValueError(f"Invalid CSV format: {str(e)}")

    def _count_csv_rows(self, file_path):
        """Fast CSV row counting"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                row_count = sum(1 for row in reader) - 1  # Exclude header
            return max(0, row_count)
        except Exception as e:
            logger.error(f"Error counting CSV rows: {str(e)}")
            return 0

    def _process_csv_chunks(self, session_id, file_path, column_mapping, total_records):
        """Process CSV in optimized chunks"""
        processed_count = 0
        chunk_size = min(self.chunk_size, 2000)  # Optimize chunk size
        total_chunks = (total_records + chunk_size - 1) // chunk_size
        current_chunk = 0

        session = ProcessingSession.query.get(session_id)
        session.total_chunks = total_chunks
        db.session.commit()

        try:
            for chunk_df in pd.read_csv(file_path, chunksize=chunk_size):
                current_chunk += 1
                chunk_processed = self._process_single_chunk(session_id, chunk_df, column_mapping, processed_count)
                processed_count += chunk_processed

                # Update progress
                session.processed_records = processed_count
                session.current_chunk = current_chunk
                db.session.commit()

                logger.info(f"Processed chunk {current_chunk}/{total_chunks}: {chunk_processed} records")

                # Small delay to prevent overwhelming the system
                if current_chunk % 5 == 0:
                    time.sleep(0.1)

        except Exception as e:
            logger.error(f"Error processing CSV chunks: {str(e)}")
            raise

        return processed_count

    def _process_single_chunk(self, session_id, chunk_df, column_mapping, start_index):
        """Process a single chunk with optimized database operations"""
        processed_count = 0
        batch_records = []

        try:
            for index, row in chunk_df.iterrows():
                try:
                    record_id = f"{session_id}_{start_index + processed_count}"

                    # Map and normalize data
                    record_data = self._map_record_data(row, column_mapping)

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
                        policy_name=record_data.get('policy_name', ''),
                        ml_risk_score=0.0,
                        risk_level='Low',
                        whitelisted=False,
                        case_status='Active'
                    )

                    batch_records.append(email_record)
                    processed_count += 1

                    # Batch insert for performance
                    if len(batch_records) >= 100:
                        db.session.add_all(batch_records)
                        db.session.flush()
                        batch_records = []

                except Exception as e:
                    logger.warning(f"Error processing record at index {index}: {str(e)}")
                    continue

            # Insert remaining records
            if batch_records:
                db.session.add_all(batch_records)
                db.session.flush()

            db.session.commit()
            logger.info(f"Successfully processed chunk: {processed_count} records")
            return processed_count

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing chunk: {str(e)}")
            raise

    def _map_record_data(self, row, column_mapping):
        """Map and normalize record data"""
        record_data = {}

        for expected_col, actual_col in column_mapping.items():
            if actual_col in row:
                value = row[actual_col]
                if pd.notna(value):
                    if expected_col in ['_time', 'termination_date']:
                        record_data[expected_col] = self._normalize_date_field(str(value).strip())
                    else:
                        record_data[expected_col] = str(value).strip()
                else:
                    record_data[expected_col] = ''
            else:
                record_data[expected_col] = ''

        return record_data

    def _apply_enhanced_workflow(self, session_id):
        """Apply workflow with improved error handling and atomic operations"""
        logger.info(f"Applying enhanced workflow for session {session_id}")

        session = ProcessingSession.query.get(session_id)
        if not session:
            logger.error(f"Session {session_id} not found during workflow")
            return

        # Step 1: Exclusion Rules
        try:
            logger.info(f"Step 1: Applying exclusion rules for session {session_id}")
            excluded_count = self.rule_engine.apply_exclusion_rules(session_id)
            session.exclusion_applied = True
            db.session.commit()
            logger.info(f"Step 1 completed: {excluded_count} records excluded")
        except Exception as e:
            logger.error(f"Step 1 failed: {str(e)}")
            session.exclusion_applied = True  # Mark as completed to prevent loops
            db.session.commit()

        # Step 2: Whitelist Filtering  
        try:
            logger.info(f"Step 2: Applying whitelist filtering for session {session_id}")
            whitelisted_count = self.domain_manager.apply_whitelist_filtering(session_id)
            session.whitelist_applied = True
            db.session.commit()
            logger.info(f"Step 2 completed: {whitelisted_count} records whitelisted")
        except Exception as e:
            logger.error(f"Step 2 failed: {str(e)}")
            session.whitelist_applied = True
            db.session.commit()

        # Step 3: Security Rules
        try:
            logger.info(f"Step 3: Applying security rules for session {session_id}")
            rule_matches = self.rule_engine.apply_security_rules(session_id)
            session.rules_applied = True
            db.session.commit()
            logger.info(f"Step 3 completed: {len(rule_matches)} rule matches")
        except Exception as e:
            logger.error(f"Step 3 failed: {str(e)}")
            session.rules_applied = True
            db.session.commit()

        # Step 4: ML Analysis
        try:
            logger.info(f"Step 4: Applying ML analysis for session {session_id}")
            analysis_results = self.ml_engine.analyze_session(session_id)
            session.ml_applied = True
            session.processing_stats = analysis_results.get('processing_stats', {})
            db.session.commit()
            logger.info(f"Step 4 completed: ML analysis finished")
        except Exception as e:
            logger.error(f"Step 4 failed: {str(e)}")
            session.ml_applied = True
            db.session.commit()

        # Ensure all workflow steps are marked as complete
        session.exclusion_applied = True
        session.whitelist_applied = True
        session.rules_applied = True
        session.ml_applied = True
        db.session.commit()

        logger.info(f"Enhanced workflow completed for session {session_id}")

    def _normalize_date_field(self, date_value):
        """Normalize date fields with better error handling"""
        if not date_value or date_value.lower() in ['', 'none', 'null', 'n/a', 'na', 'nil']:
            return ''

        try:
            from dateutil import parser
            parsed_date = parser.parse(date_value, fuzzy=True)
            return parsed_date.strftime('%Y-%m-%d %H:%M:%S')
        except:
            try:
                parsed_date = pd.to_datetime(date_value, errors='coerce')
                if pd.notna(parsed_date):
                    return parsed_date.strftime('%Y-%m-%d %H:%M:%S')
            except:
                pass

            logger.warning(f"Could not parse date value: {date_value}")
            return str(date_value)

    def _handle_processing_error(self, session_id, error_message):
        """Handle processing errors gracefully"""
        try:
            session = ProcessingSession.query.get(session_id)
            if session:
                session.status = 'error'
                session.error_message = error_message
                db.session.commit()

            # Log error for debugging
            error_record = ProcessingError(
                session_id=session_id,
                error_type='processing_error',
                error_message=error_message,
                record_data={'timestamp': datetime.utcnow().isoformat()}
            )
            db.session.add(error_record)
            db.session.commit()

        except Exception as e:
            logger.error(f"Error handling processing error: {str(e)}")

    def fix_stuck_session(self, session_id):
        """Fix a stuck processing session"""
        try:
            logger.info(f"Attempting to fix stuck session {session_id}")

            session = ProcessingSession.query.get(session_id)
            if not session:
                logger.error(f"Session {session_id} not found")
                return False

            # Check if records exist
            record_count = EmailRecord.query.filter_by(session_id=session_id).count()

            if record_count > 0:
                logger.info(f"Found {record_count} records for session {session_id}")

                # Apply workflow if not completed
                if not all([session.exclusion_applied, session.whitelist_applied, 
                           session.rules_applied, session.ml_applied]):
                    self._apply_enhanced_workflow(session_id)

                # Mark as completed
                session.status = 'completed'
                session.processed_records = record_count
                session.completed_at = datetime.utcnow()
                db.session.commit()

                logger.info(f"Successfully fixed stuck session {session_id}")
                return True
            else:
                logger.warning(f"No records found for session {session_id}, marking as error")
                session.status = 'error'
                session.error_message = 'No records processed'
                db.session.commit()
                return False

        except Exception as e:
            logger.error(f"Error fixing stuck session {session_id}: {str(e)}")
            return False