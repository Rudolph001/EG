from app import db
from datetime import datetime
from sqlalchemy import Text, JSON
import json

class ProcessingSession(db.Model):
    __tablename__ = 'processing_sessions'
    
    id = db.Column(db.String(36), primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    total_records = db.Column(db.Integer, default=0)
    processed_records = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default='uploaded')  # uploaded, processing, completed, error
    error_message = db.Column(Text)
    processing_stats = db.Column(JSON)
    data_path = db.Column(db.String(500))
    is_compressed = db.Column(db.Boolean, default=False)
    
    # 8-Stage Processing workflow
    current_stage = db.Column(db.Integer, default=0)  # 0-8 workflow stages
    stage_progress = db.Column(db.Float, default=0.0)  # 0-100 percentage
    workflow_stages = db.Column(JSON)  # Track each stage status
    
    # Legacy workflow stages (for backward compatibility)
    exclusion_applied = db.Column(db.Boolean, default=False)
    whitelist_applied = db.Column(db.Boolean, default=False)
    rules_applied = db.Column(db.Boolean, default=False)
    ml_applied = db.Column(db.Boolean, default=False)
    
    # Chunk tracking
    current_chunk = db.Column(db.Integer, default=0)
    total_chunks = db.Column(db.Integer, default=0)
    
    def __repr__(self):
        return f'<ProcessingSession {self.id}>'

class EmailRecord(db.Model):
    __tablename__ = 'email_records'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), db.ForeignKey('processing_sessions.id'), nullable=False)
    record_id = db.Column(db.String(100), nullable=False)  # Unique within session
    
    # Original CSV fields
    time = db.Column(db.String(100))
    sender = db.Column(db.String(255))
    subject = db.Column(Text)
    attachments = db.Column(Text)
    recipients = db.Column(Text)
    recipients_email_domain = db.Column(db.String(255))
    leaver = db.Column(db.String(10))
    termination_date = db.Column(db.String(100))
    wordlist_attachment = db.Column(Text)
    wordlist_subject = db.Column(Text)
    bunit = db.Column(db.String(255))
    department = db.Column(db.String(255))
    status = db.Column(db.String(100))
    user_response = db.Column(Text)
    final_outcome = db.Column(db.String(255))
    justification = db.Column(Text)
    policy_name = db.Column(db.String(255))
    
    # Processing results
    excluded_by_rule = db.Column(db.String(500))
    whitelisted = db.Column(db.Boolean, default=False)
    rule_matches = db.Column(Text)  # JSON string of matched rules
    ml_risk_score = db.Column(db.Float)
    ml_anomaly_score = db.Column(db.Float)
    risk_level = db.Column(db.String(20))  # Critical, High, Medium, Low
    ml_explanation = db.Column(Text)
    
    # Case management
    case_status = db.Column(db.String(20), default='Active')  # Active, Cleared, Escalated
    assigned_to = db.Column(db.String(255))
    notes = db.Column(Text)
    escalated_at = db.Column(db.DateTime)
    resolved_at = db.Column(db.DateTime)
    
    # Flag tracking
    is_flagged = db.Column(db.Boolean, default=False)
    flag_reason = db.Column(Text)
    flagged_at = db.Column(db.DateTime)
    flagged_by = db.Column(db.String(255))
    previously_flagged = db.Column(db.Boolean, default=False)  # Flagged in previous import
    
    def __repr__(self):
        return f'<EmailRecord {self.record_id}>'

class Rule(db.Model):
    __tablename__ = 'rules'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(Text)
    rule_type = db.Column(db.String(50), nullable=False)  # security, exclusion
    conditions = db.Column(JSON)  # JSON structure for complex conditions
    actions = db.Column(JSON)  # JSON structure for actions
    priority = db.Column(db.Integer, default=1)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Rule {self.name}>'

class WhitelistDomain(db.Model):
    __tablename__ = 'whitelist_domains'
    
    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(255), unique=True, nullable=False)
    domain_type = db.Column(db.String(50))  # Corporate, Personal, Public, Suspicious
    added_by = db.Column(db.String(255))
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(Text)
    is_active = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<WhitelistDomain {self.domain}>'

class AttachmentKeyword(db.Model):
    __tablename__ = 'attachment_keywords'
    
    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # Business, Personal, Suspicious
    risk_score = db.Column(db.Integer, default=1)  # 1-10 scale
    keyword_type = db.Column(db.String(20), default='risk')  # risk, exclusion
    applies_to = db.Column(db.String(20), default='both')  # subject, attachment, both
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<AttachmentKeyword {self.keyword}>'

class RiskFactor(db.Model):
    __tablename__ = 'risk_factors'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    description = db.Column(Text, nullable=False)
    max_score = db.Column(db.Float, nullable=False, default=0.1)
    category = db.Column(db.String(50), nullable=False, default='General')  # General, Security, Content, Time
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    weight_percentage = db.Column(db.Float, default=0.0)  # Percentage of total risk score
    
    # Configuration for how this factor is calculated
    calculation_config = db.Column(JSON)  # JSON config for calculation rules
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<RiskFactor {self.name}>'

class ProcessingError(db.Model):
    __tablename__ = 'processing_errors'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), db.ForeignKey('processing_sessions.id'), nullable=False)
    error_type = db.Column(db.String(100), nullable=False)
    error_message = db.Column(Text, nullable=False)
    record_data = db.Column(JSON)  # Store problematic record data
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    resolved = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<ProcessingError {self.error_type}>'

class FlaggedEvent(db.Model):
    __tablename__ = 'flagged_events'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_email = db.Column(db.String(255), nullable=False, index=True)
    original_session_id = db.Column(db.String(36), nullable=False)
    original_record_id = db.Column(db.String(100), nullable=False)
    flag_reason = db.Column(Text, nullable=False)
    flagged_by = db.Column(db.String(255), default='System User')
    flagged_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Optional: Store original email details for reference
    original_subject = db.Column(Text)
    original_recipients_domain = db.Column(db.String(255))
    original_risk_level = db.Column(db.String(20))
    original_ml_score = db.Column(db.Float)
    
    def __repr__(self):
        return f'<FlaggedEvent {self.sender_email}>'
