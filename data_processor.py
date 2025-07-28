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

                    self.expected_columns = [
                        '_time', 'sender', 'subject', 'attachments', 'recipients',
                        'recipients_email_domain', 'leaver', 'termination_date',
                        'wordlist_attachment', 'wordlist_subject', 'bunit',
                        'department', 'status', 'user_response', 'final_outcome',
                        'justification', 'policy_name'
                    ]

                def process_csv(self, session_id, file_path):
                    try:
                        logger.info(f"Starting CSV processing for session {session_id}")
                        session = ProcessingSession.query.get(session_id)
                        if not session:
                            logger.error(f"Session {session_id} not found")
                            return

                        if session.status in ['processing', 'completed']:
                            logger.warning(f"Session {session_id} is already being processed or completed, skipping")
                            return

                        session.status = 'processing'
                        db.session.commit()

                        column_mapping = self._validate_csv_structure(file_path)
                        total_records = self._count_csv_rows(file_path)
                        session.total_records = total_records
                        db.session.commit()

                        processed_count = 0
                        chunk_size = self.chunk_size if self.enable_fast_mode else min(500, self.chunk_size)
                        total_chunks = (total_records + chunk_size - 1) // chunk_size
                        current_chunk = 0

                        for chunk_df in pd.read_csv(file_path, chunksize=chunk_size):
                            try:
                                current_chunk += 1
                                chunk_processed = self._process_chunk(session_id, chunk_df, column_mapping, processed_count)
                                processed_count += chunk_processed

                                session.processed_records = processed_count
                                session.current_chunk = current_chunk
                                session.total_chunks = total_chunks
                                db.session.commit()

                                logger.info(f"Completed chunk {current_chunk}/{total_chunks} - {chunk_processed} records processed")

                            except Exception as chunk_error:
                                logger.warning(f"Error processing chunk {current_chunk}: {str(chunk_error)}")
                                continue

                        self._apply_workflow(session_id)

                        session.status = 'completed'
                        session.processed_records = processed_count
                        session.exclusion_applied = True
                        session.whitelist_applied = True
                        session.rules_applied = True
                        session.ml_applied = True
                        session.completed_at = datetime.utcnow()
                        db.session.commit()

                        logger.info(f"Session {session_id} marked as completed with {processed_count} records")

                    except Exception as e:
                        logger.error(f"Error processing CSV for session {session_id}: {str(e)}")
                        session = ProcessingSession.query.get(session_id)
                        if session:
                            session.status = 'error'
                            session.error_message = str(e)
                            db.session.commit()
                        raise

                def _process_chunk(self, session_id, chunk_df, column_mapping, start_index):
                    processed_count = 0
                    email_records = []

                    for index, row in chunk_df.iterrows():
                        try:
                            record_id = f"{session_id}_{start_index + processed_count}"
                            record_data = {}

                            for expected_col, actual_col in column_mapping.items():
                                value = row.get(actual_col, '')
                                value = str(value).strip() if pd.notna(value) else ''
                                if expected_col in ['_time', 'termination_date']:
                                    record_data[expected_col] = self._normalize_date_field(value)
                                else:
                                    record_data[expected_col] = value

                            # TEMP EmailRecord to evaluate rules
                            temp_record = EmailRecord(
                                session_id=session_id,
                                record_id=record_id,
                                **{col: record_data.get(col, '') for col in self.expected_columns},
                                ml_risk_score=0.0,
                                risk_level='Low',
                                whitelisted=False,
                                case_status='Active'
                            )

                            if self.rule_engine.is_excluded(temp_record):
                                continue  # Skip record

                            if self.domain_manager.is_whitelisted(temp_record):
                                continue  # Skip record

                            email_records.append(temp_record)
                            processed_count += 1

                        except Exception as e:
                            logger.warning(f"Error processing record at index {index}: {str(e)}")
                            try:
                                error = ProcessingError(
                                    session_id=session_id,
                                    error_type='record_processing',
                                    error_message=str(e),
                                    record_data={'index': int(index), 'error': str(e)}
                                )
                                db.session.add(error)
                            except:
                                pass

                    try:
                        if email_records:
                            db.session.bulk_save_objects(email_records)
                            db.session.commit()
                            logger.info(f"Successfully processed and saved {processed_count} records to database")
                    except Exception as e:
                        db.session.rollback()
                        logger.error(f"Error committing chunk: {str(e)}")
                        raise

                    return processed_count

                def _apply_workflow(self, session_id):
                    try:
                        logger.info(f"Applying workflow for session {session_id}")
                        session = ProcessingSession.query.get(session_id)
                        if not session:
                            logger.error(f"Session {session_id} not found during workflow")
                            return

                        self._apply_security_rules(session_id)
                        self._apply_ml_analysis(session_id)

                    except Exception as e:
                        logger.error(f"Critical error applying workflow for session {session_id}: {str(e)}")
                        session = ProcessingSession.query.get(session_id)
                        if session:
                            session.exclusion_applied = True
                            session.whitelist_applied = True
                            session.rules_applied = True
                            session.ml_applied = True
                            db.session.commit()
                        raise

                def _apply_security_rules(self, session_id):
                    try:
                        logger.info(f"Applying security rules for session {session_id}")
                        self.rule_engine.apply_security_rules(session_id)
                    except Exception as e:
                        logger.error(f"Error applying security rules: {str(e)}")
                        raise

                def _apply_ml_analysis(self, session_id):
                    try:
                        logger.info(f"Applying ML analysis for session {session_id}")
                        analysis_results = self.ml_engine.analyze_session(session_id)
                        session = ProcessingSession.query.get(session_id)
                        if session:
                            session.processing_stats = analysis_results.get('processing_stats', {})
                            db.session.commit()
                    except Exception as e:
                        logger.error(f"Error applying ML analysis: {str(e)}")
                        raise

                def _validate_csv_structure(self, file_path):
                    try:
                        sample_df = pd.read_csv(file_path, nrows=5)
                        column_mapping = {}
                        for expected_col in self.expected_columns:
                            for actual_col in sample_df.columns:
                                if actual_col.lower().strip() == expected_col.lower():
                                    column_mapping[expected_col] = actual_col
                                    break
                        logger.info(f"CSV validation successful. Column mapping: {column_mapping}")
                        return column_mapping
                    except Exception as e:
                        logger.error(f"CSV validation failed: {str(e)}")
                        raise

                def _count_csv_rows(self, file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            return max(0, sum(1 for row in csv.reader(f)) - 1)
                    except Exception as e:
                        logger.error(f"Error counting CSV rows: {str(e)}")
                        return 0

                def _normalize_date_field(self, date_value):
                    if not date_value or date_value.lower() in ['', 'null', 'none', 'n/a']:
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
                        logger.warning(f"Could not parse date value: {date_value}, keeping original")
                        return str(date_value)
