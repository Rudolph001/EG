"""
Email Guardian Audit System
Tracks all system changes and user actions for compliance and monitoring
"""

import json
from datetime import datetime
from models import db
from flask import g, request, session
import os

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id = db.Column(db.String(100))  # Session or user identifier
    action_type = db.Column(db.String(50), nullable=False)  # CREATE, UPDATE, DELETE, VIEW, EXPORT, etc.
    resource_type = db.Column(db.String(50), nullable=False)  # SESSION, CASE, REPORT, CONFIG, etc.
    resource_id = db.Column(db.String(100))  # ID of the affected resource
    details = db.Column(db.Text)  # JSON string with additional details
    ip_address = db.Column(db.String(45))  # Support both IPv4 and IPv6
    user_agent = db.Column(db.String(500))
    severity = db.Column(db.String(20), default='INFO')  # INFO, WARNING, CRITICAL
    session_id = db.Column(db.String(100))  # Processing session if applicable
    
    def __repr__(self):
        return f'<AuditLog {self.id}: {self.action_type} {self.resource_type}>'

class AuditLogger:
    """Centralized audit logging system"""
    
    @staticmethod
    def log_action(action_type, resource_type, resource_id=None, details=None, severity='INFO'):
        """Log an audit event"""
        try:
            # Get user context
            user_id = session.get('user_id', 'anonymous')
            ip_address = request.remote_addr if request else None
            user_agent = request.headers.get('User-Agent', '') if request else ''
            session_id = session.get('current_session_id')
            
            # Prepare details
            if details and not isinstance(details, str):
                details = json.dumps(details, default=str)
            
            # Create audit log entry
            audit_entry = AuditLog(
                user_id=user_id,
                action_type=action_type,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else None,  # Truncate if too long
                severity=severity,
                session_id=session_id
            )
            
            db.session.add(audit_entry)
            db.session.commit()
            
            return audit_entry
            
        except Exception as e:
            print(f"Error logging audit event: {str(e)}")
            return None
    
    @staticmethod
    def log_session_upload(session_id, filename, record_count):
        """Log CSV file upload"""
        AuditLogger.log_action(
            action_type='UPLOAD',
            resource_type='SESSION',
            resource_id=session_id,
            details={
                'filename': filename,
                'record_count': record_count,
                'action': 'CSV file uploaded and processed'
            }
        )
    
    @staticmethod
    def log_case_action(action, session_id, case_id=None, details=None):
        """Log case-related actions"""
        AuditLogger.log_action(
            action_type=action.upper(),
            resource_type='CASE',
            resource_id=case_id,
            details={
                'session_id': session_id,
                'action_details': details
            }
        )
    
    @staticmethod
    def log_escalation(session_id, record_id, reason):
        """Log email escalation"""
        AuditLogger.log_action(
            action_type='ESCALATE',
            resource_type='EMAIL',
            resource_id=record_id,
            details={
                'session_id': session_id,
                'escalation_reason': reason,
                'action': 'Email escalated for review'
            },
            severity='WARNING'
        )
    
    @staticmethod
    def log_clear_case(session_id, record_id, reason=None):
        """Log case clearance"""
        AuditLogger.log_action(
            action_type='CLEAR',
            resource_type='CASE',
            resource_id=record_id,
            details={
                'session_id': session_id,
                'clear_reason': reason,
                'action': 'Case marked as cleared'
            }
        )
    
    @staticmethod
    def log_configuration_change(config_type, old_value, new_value, changed_by=None):
        """Log system configuration changes"""
        AuditLogger.log_action(
            action_type='CONFIG_CHANGE',
            resource_type='CONFIGURATION',
            resource_id=config_type,
            details={
                'config_type': config_type,
                'old_value': old_value,
                'new_value': new_value,
                'changed_by': changed_by
            },
            severity='WARNING'
        )
    
    @staticmethod
    def log_report_generation(report_type, session_ids=None, format_type='HTML'):
        """Log report generation"""
        AuditLogger.log_action(
            action_type='GENERATE',
            resource_type='REPORT',
            details={
                'report_type': report_type,
                'sessions_included': session_ids,
                'format': format_type,
                'action': f'{report_type} report generated'
            }
        )
    
    @staticmethod
    def log_export_action(export_type, session_id, format_type='CSV'):
        """Log data export"""
        AuditLogger.log_action(
            action_type='EXPORT',
            resource_type='DATA',
            resource_id=session_id,
            details={
                'export_type': export_type,
                'format': format_type,
                'session_id': session_id
            }
        )
    
    @staticmethod
    def log_ml_training(session_id, model_type, performance_metrics=None):
        """Log ML model training"""
        AuditLogger.log_action(
            action_type='ML_TRAIN',
            resource_type='MODEL',
            resource_id=session_id,
            details={
                'model_type': model_type,
                'session_id': session_id,
                'performance_metrics': performance_metrics
            }
        )
    
    @staticmethod
    def log_user_feedback(session_id, feedback_type, details=None):
        """Log user feedback and decisions"""
        AuditLogger.log_action(
            action_type='FEEDBACK',
            resource_type='USER_DECISION',
            resource_id=session_id,
            details={
                'feedback_type': feedback_type,
                'session_id': session_id,
                'details': details
            }
        )
    
    @staticmethod
    def get_audit_summary(days=30):
        """Get audit summary for reporting"""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        logs = AuditLog.query.filter(AuditLog.timestamp >= cutoff_date).all()
        
        summary = {
            'total_actions': len(logs),
            'actions_by_type': {},
            'actions_by_severity': {'INFO': 0, 'WARNING': 0, 'CRITICAL': 0},
            'recent_critical': [],
            'top_users': {},
            'sessions_affected': set(),
            'time_range': {
                'start': cutoff_date.isoformat(),
                'end': datetime.utcnow().isoformat()
            }
        }
        
        for log in logs:
            # Count by action type
            if log.action_type not in summary['actions_by_type']:
                summary['actions_by_type'][log.action_type] = 0
            summary['actions_by_type'][log.action_type] += 1
            
            # Count by severity
            summary['actions_by_severity'][log.severity] += 1
            
            # Track critical actions
            if log.severity == 'CRITICAL':
                summary['recent_critical'].append({
                    'timestamp': log.timestamp.isoformat(),
                    'action': f"{log.action_type} {log.resource_type}",
                    'details': log.details
                })
            
            # Count by user
            if log.user_id not in summary['top_users']:
                summary['top_users'][log.user_id] = 0
            summary['top_users'][log.user_id] += 1
            
            # Track affected sessions
            if log.session_id:
                summary['sessions_affected'].add(log.session_id)
        
        summary['sessions_affected'] = len(summary['sessions_affected'])
        return summary

# Initialize audit system
def init_audit_system(app):
    """Initialize audit system with the Flask app"""
    with app.app_context():
        db.create_all()
        
        # Log system startup
        AuditLogger.log_action(
            action_type='SYSTEM_START',
            resource_type='APPLICATION',
            details={'message': 'Email Guardian system started'},
            severity='INFO'
        )