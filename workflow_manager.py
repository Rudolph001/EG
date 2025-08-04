"""
Workflow Manager for Email Guardian Processing Pipeline
Handles the 8-stage sequential workflow for CSV processing
"""

import json
import logging
from datetime import datetime
from models import ProcessingSession
from app import db

logger = logging.getLogger(__name__)

class WorkflowManager:
    """Manages the 8-stage sequential workflow for email processing"""
    
    # Define the 8 workflow stages with their progress ranges
    WORKFLOW_STAGES = {
        1: {
            'name': 'Data Ingestion',
            'description': 'Loading and parsing CSV file',
            'progress_start': 0,
            'progress_end': 5,
            'icon': 'fas fa-upload'
        },
        2: {
            'name': 'Exclusion Rules',
            'description': 'Applying exclusion rules and filters',
            'progress_start': 5,
            'progress_end': 20,
            'icon': 'fas fa-filter'
        },
        3: {
            'name': 'Whitelist Filtering',
            'description': 'Processing domain whitelist',
            'progress_start': 20,
            'progress_end': 35,
            'icon': 'fas fa-shield-alt'
        },
        4: {
            'name': 'Security Rules',
            'description': 'Applying security rules engine',
            'progress_start': 35,
            'progress_end': 50,
            'icon': 'fas fa-shield-virus'
        },
        5: {
            'name': 'Wordlist Analysis',
            'description': 'Analyzing keywords and content',
            'progress_start': 50,
            'progress_end': 65,
            'icon': 'fas fa-list-alt'
        },
        6: {
            'name': 'ML Analysis',
            'description': 'Machine learning risk assessment',
            'progress_start': 65,
            'progress_end': 80,
            'icon': 'fas fa-brain'
        },
        7: {
            'name': 'Case Generation',
            'description': 'Creating security cases',
            'progress_start': 80,
            'progress_end': 90,
            'icon': 'fas fa-folder-open'
        },
        8: {
            'name': 'Final Validation',
            'description': 'Validating and finalizing results',
            'progress_start': 90,
            'progress_end': 100,
            'icon': 'fas fa-check-circle'
        }
    }
    
    def __init__(self):
        """Initialize workflow manager"""
        pass
    
    def initialize_workflow(self, session_id):
        """Initialize workflow stages for a new session"""
        try:
            session = ProcessingSession.query.get(session_id)
            if not session:
                raise Exception(f"Session {session_id} not found")
            
            # Initialize workflow stages
            workflow_stages = {}
            for stage_num, stage_info in self.WORKFLOW_STAGES.items():
                workflow_stages[str(stage_num)] = {
                    'name': stage_info['name'],
                    'description': stage_info['description'],
                    'status': 'waiting',  # waiting, processing, complete, error
                    'progress': 0,
                    'started_at': None,
                    'completed_at': None,
                    'icon': stage_info['icon'],
                    'error_message': None
                }
            
            # Update session
            session.current_stage = 0
            session.stage_progress = 0.0
            session.workflow_stages = workflow_stages
            db.session.commit()
            
            logger.info(f"Initialized workflow for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing workflow for session {session_id}: {str(e)}")
            return False
    
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
    
    def start_stage(self, session_id, stage_number):
        """Start a specific workflow stage with improved error handling"""
        try:
            session = self._get_session_with_retry(session_id)
            if not session:
                raise Exception(f"Session {session_id} not found")
            
            if not session.workflow_stages:
                self.initialize_workflow(session_id)
                session = self._get_session_with_retry(session_id)
            
            workflow_stages = session.workflow_stages.copy()
            stage_key = str(stage_number)
            
            if stage_key not in workflow_stages:
                raise Exception(f"Invalid stage number: {stage_number}")
            
            # Complete previous stages if they're not already complete
            for i in range(1, stage_number):
                prev_stage_key = str(i)
                if workflow_stages[prev_stage_key]['status'] != 'complete':
                    workflow_stages[prev_stage_key]['status'] = 'complete'
                    workflow_stages[prev_stage_key]['completed_at'] = datetime.utcnow().isoformat()
            
            # Start current stage
            workflow_stages[stage_key]['status'] = 'processing'
            workflow_stages[stage_key]['started_at'] = datetime.utcnow().isoformat()
            workflow_stages[stage_key]['progress'] = 0
            
            # Update session
            session.current_stage = stage_number
            session.workflow_stages = workflow_stages
            session.stage_progress = self.WORKFLOW_STAGES[stage_number]['progress_start']
            self._commit_with_retry()
            
            logger.info(f"Started stage {stage_number} ({self.WORKFLOW_STAGES[stage_number]['name']}) for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error starting stage {stage_number} for session {session_id}: {str(e)}")
            return False
    
    def update_stage_progress(self, session_id, stage_number, progress_percent):
        """Update progress within a specific stage with improved error handling"""
        try:
            session = self._get_session_with_retry(session_id)
            if not session:
                return False
            
            if not session.workflow_stages:
                return False
            
            workflow_stages = session.workflow_stages.copy()
            stage_key = str(stage_number)
            
            if stage_key not in workflow_stages:
                return False
            
            # Update stage progress
            workflow_stages[stage_key]['progress'] = progress_percent
            
            # Calculate overall progress
            stage_info = self.WORKFLOW_STAGES[stage_number]
            progress_range = stage_info['progress_end'] - stage_info['progress_start']
            stage_contribution = (progress_percent / 100) * progress_range
            overall_progress = stage_info['progress_start'] + stage_contribution
            
            # Update session
            session.workflow_stages = workflow_stages
            session.stage_progress = overall_progress
            self._commit_with_retry()
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating stage progress for session {session_id}: {str(e)}")
            return False
    
    def complete_stage(self, session_id, stage_number):
        """Complete a workflow stage with improved error handling"""
        try:
            session = self._get_session_with_retry(session_id)
            if not session:
                return False
            
            if not session.workflow_stages:
                return False
            
            workflow_stages = session.workflow_stages.copy()
            stage_key = str(stage_number)
            
            if stage_key not in workflow_stages:
                return False
            
            # Complete stage
            workflow_stages[stage_key]['status'] = 'complete'
            workflow_stages[stage_key]['completed_at'] = datetime.utcnow().isoformat()
            workflow_stages[stage_key]['progress'] = 100
            
            # Update session
            session.workflow_stages = workflow_stages
            session.stage_progress = self.WORKFLOW_STAGES[stage_number]['progress_end']
            
            # If this is the final stage, mark session as completed
            if stage_number == 8:
                session.status = 'completed'
                session.stage_progress = 100.0
            
            self._commit_with_retry()
            
            logger.info(f"Completed stage {stage_number} ({self.WORKFLOW_STAGES[stage_number]['name']}) for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error completing stage {stage_number} for session {session_id}: {str(e)}")
            return False
    
    def error_stage(self, session_id, stage_number, error_message):
        """Mark a workflow stage as failed"""
        try:
            session = ProcessingSession.query.get(session_id)
            if not session:
                return False
            
            if not session.workflow_stages:
                return False
            
            workflow_stages = session.workflow_stages.copy()
            stage_key = str(stage_number)
            
            if stage_key not in workflow_stages:
                return False
            
            # Mark stage as error
            workflow_stages[stage_key]['status'] = 'error'
            workflow_stages[stage_key]['error_message'] = error_message
            
            # Update session
            session.workflow_stages = workflow_stages
            session.status = 'error'
            session.error_message = f"Stage {stage_number} ({self.WORKFLOW_STAGES[stage_number]['name']}): {error_message}"
            db.session.commit()
            
            logger.error(f"Error in stage {stage_number} for session {session_id}: {error_message}")
            return True
            
        except Exception as e:
            logger.error(f"Error marking stage error for session {session_id}: {str(e)}")
            return False
    
    def get_workflow_status(self, session_id):
        """Get current workflow status"""
        try:
            session = ProcessingSession.query.get(session_id)
            if not session:
                return None
            
            if not session.workflow_stages:
                self.initialize_workflow(session_id)
                session = ProcessingSession.query.get(session_id)
            
            # Get record counts for each stage
            stage_counts = self._get_stage_record_counts(session_id)
            
            # Ensure workflow stages are properly structured
            workflow_stages = session.workflow_stages or {}
            current_stage = session.current_stage or 0
            
            # Update stage progress based on current processing state
            for stage_num in range(1, 9):
                stage_key = str(stage_num)
                if stage_key not in workflow_stages:
                    continue
                    
                stage = workflow_stages[stage_key]
                
                # Add record count to stage
                stage['record_count'] = stage_counts.get(stage_num, 0)
                stage['record_count_text'] = self._format_record_count(stage_counts.get(stage_num, 0), stage_num)
                
                # Mark completed stages
                if stage_num < current_stage:
                    stage['status'] = 'complete'
                    stage['progress'] = 100
                    if not stage.get('completed_at'):
                        stage['completed_at'] = datetime.utcnow().isoformat()
                
                # Mark current stage as processing
                elif stage_num == current_stage:
                    if session.status == 'processing':
                        stage['status'] = 'processing'
                        # Calculate progress within stage based on overall progress
                        stage_info = self.WORKFLOW_STAGES.get(stage_num, {})
                        progress_start = stage_info.get('progress_start', 0)
                        progress_end = stage_info.get('progress_end', 100)
                        overall_progress = session.stage_progress or 0
                        
                        if progress_end > progress_start:
                            stage_progress = ((overall_progress - progress_start) / (progress_end - progress_start)) * 100
                            stage['progress'] = max(0, min(100, stage_progress))
                        else:
                            stage['progress'] = 50  # Default processing progress
                        
                        if not stage.get('started_at'):
                            stage['started_at'] = datetime.utcnow().isoformat()
                    elif session.status == 'completed':
                        stage['status'] = 'complete'
                        stage['progress'] = 100
                        if not stage.get('completed_at'):
                            stage['completed_at'] = datetime.utcnow().isoformat()
                
                # Future stages remain waiting
                else:
                    if stage['status'] not in ['complete', 'processing']:
                        stage['status'] = 'waiting'
                        stage['progress'] = 0
            
            return {
                'session_id': session_id,
                'current_stage': current_stage,
                'overall_progress': round(session.stage_progress or 0, 1),
                'status': session.status,
                'stages': workflow_stages,
                'total_stages': len(self.WORKFLOW_STAGES),
                'estimated_time_remaining': self._estimate_time_remaining(session)
            }
            
        except Exception as e:
            logger.error(f"Error getting workflow status for session {session_id}: {str(e)}")
            return None
    
    def _estimate_time_remaining(self, session):
        """Estimate remaining processing time"""
        try:
            if not session.upload_time or session.status != 'processing':
                return None
                
            elapsed_time = (datetime.utcnow() - session.upload_time).total_seconds()
            progress = session.stage_progress or 0
            
            if progress <= 0:
                return None
                
            # Estimate total time based on current progress
            estimated_total_time = elapsed_time / (progress / 100)
            remaining_time = max(0, estimated_total_time - elapsed_time)
            
            return int(remaining_time)
            
        except Exception as e:
            logger.warning(f"Error estimating time remaining: {str(e)}")
            return None
    
    def _get_stage_record_counts(self, session_id):
        """Get record counts for each workflow stage"""
        try:
            from models import EmailRecord
            
            # Get total records
            total_records = EmailRecord.query.filter_by(session_id=session_id).count()
            
            # Get excluded records (stage 2)
            excluded_records = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.excluded_by_rule.isnot(None)
            ).count()
            
            # Get whitelisted records (stage 3)
            whitelisted_records = EmailRecord.query.filter_by(
                session_id=session_id,
                whitelisted=True
            ).count()
            
            # Get records with rule matches (stage 4)
            rule_matched_records = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.rule_matches.isnot(None)
            ).count()
            
            # Get records with wordlist matches (stage 5)
            wordlist_records = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                db.or_(
                    EmailRecord.wordlist_subject.isnot(None),
                    EmailRecord.wordlist_attachment.isnot(None)
                )
            ).count()
            
            # Get ML analyzed records (stage 6)
            ml_analyzed_records = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.ml_risk_score.isnot(None)
            ).count()
            
            # Get security cases (stage 7)
            security_cases = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.risk_level.in_(['Critical', 'High', 'Medium'])
            ).count()
            
            # Get validated records (stage 8)
            validated_records = EmailRecord.query.filter_by(
                session_id=session_id
            ).count()
            
            return {
                1: total_records,           # Data Ingestion
                2: excluded_records,        # Exclusion Rules  
                3: whitelisted_records,     # Whitelist Filtering
                4: rule_matched_records,    # Security Rules
                5: wordlist_records,        # Wordlist Analysis
                6: ml_analyzed_records,     # ML Analysis
                7: security_cases,          # Case Generation
                8: validated_records        # Final Validation
            }
            
        except Exception as e:
            logger.error(f"Error getting stage record counts: {str(e)}")
            return {i: 0 for i in range(1, 9)}
    
    def _format_record_count(self, count, stage_num):
        """Format record count text for display"""
        stage_labels = {
            1: 'records loaded',
            2: 'records excluded', 
            3: 'records whitelisted',
            4: 'rule matches',
            5: 'wordlist matches',
            6: 'records analyzed',
            7: 'cases generated',
            8: 'records validated'
        }
        
        if count == 0:
            return f"0 {stage_labels.get(stage_num, 'records')}"
        elif count == 1:
            label = stage_labels.get(stage_num, 'records').replace('records', 'record')
            return f"1 {label}"
        else:
            return f"{count:,} {stage_labels.get(stage_num, 'records')}"

    def reset_workflow(self, session_id):
        """Reset workflow to initial state"""
        try:
            session = ProcessingSession.query.get(session_id)
            if not session:
                return False
            
            session.current_stage = 0
            session.stage_progress = 0.0
            session.workflow_stages = None
            session.status = 'uploaded'
            db.session.commit()
            
            logger.info(f"Reset workflow for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting workflow for session {session_id}: {str(e)}")
            return False