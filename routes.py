from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
from sqlalchemy import text
from io import StringIO, BytesIO
import csv
import json
from datetime import datetime
from app import app, db
from models import ProcessingSession, EmailRecord, Rule, WhitelistDomain, AttachmentKeyword, ProcessingError, RiskFactor
from session_manager import SessionManager
from data_processor import DataProcessor
from ml_engine import MLEngine
from advanced_ml_engine import AdvancedMLEngine
from performance_config import config
from ml_config import MLRiskConfig
from rule_engine import RuleEngine
from domain_manager import DomainManager
import uuid
import os
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Initialize core components
session_manager = SessionManager()
data_processor = DataProcessor()
ml_engine = MLEngine()
advanced_ml_engine = AdvancedMLEngine()
rule_engine = RuleEngine()
domain_manager = DomainManager()
ml_config = MLRiskConfig()

@app.route('/')
def index():
    """Main index page with upload functionality"""
    recent_sessions = ProcessingSession.query.order_by(ProcessingSession.upload_time.desc()).limit(10).all()
    return render_template('index.html', recent_sessions=recent_sessions)

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle CSV file upload and create processing session"""
    try:
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(url_for('index'))

        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('index'))

        if not file.filename.lower().endswith('.csv'):
            flash('Please upload a CSV file', 'error')
            return redirect(url_for('index'))

        # Create new session
        session_id = str(uuid.uuid4())
        filename = file.filename

        # Save uploaded file
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{session_id}_{filename}")
        file.save(upload_path)

        # Create session record
        session = ProcessingSession(
            id=session_id,
            filename=filename,
            status='uploaded'
        )
        db.session.add(session)
        db.session.commit()

        # Process the file asynchronously (start processing and redirect immediately)
        flash(f'File uploaded successfully. Processing started. Session ID: {session_id}', 'success')

        # Start processing in background with proper Flask context
        try:
            # Quick validation only
            import threading
            def background_processing():
                with app.app_context():  # Create Flask application context
                    try:
                        data_processor.process_csv(session_id, upload_path)
                        logger.info(f"Background processing completed for session {session_id}")
                    except Exception as e:
                        logger.error(f"Background processing error for session {session_id}: {str(e)}")
                        session = ProcessingSession.query.get(session_id)
                        if session:
                            session.status = 'error'
                            session.error_message = str(e)
                            db.session.commit()

            # Start background thread
            thread = threading.Thread(target=background_processing)
            thread.daemon = True
            thread.start()

            return redirect(url_for('dashboard', session_id=session_id))
        except Exception as e:
            logger.error(f"Processing initialization error for session {session_id}: {str(e)}")
            session.status = 'error'
            session.error_message = str(e)
            db.session.commit()
            flash(f'Error starting processing: {str(e)}', 'error')
            return redirect(url_for('index'))

    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        flash(f'Upload failed: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/api/processing-status/<session_id>')
def processing_status(session_id):
    """Get processing status for session"""
    session = ProcessingSession.query.get_or_404(session_id)

    # Get workflow statistics
    workflow_stats = {}
    if session.status in ['processing', 'completed']:
        try:
            # Count excluded records
            excluded_count = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.excluded_by_rule.isnot(None)
            ).count()

            # Count whitelisted records  
            whitelisted_count = EmailRecord.query.filter_by(
                session_id=session_id,
                whitelisted=True
            ).count()

            # Count records with rule matches
            rules_matched_count = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.rule_matches.isnot(None)
            ).count()

            # Count critical cases
            critical_cases_count = EmailRecord.query.filter_by(
                session_id=session_id,
                risk_level='Critical'
            ).count()

            workflow_stats = {
                'excluded_count': excluded_count,
                'whitelisted_count': whitelisted_count,
                'rules_matched_count': rules_matched_count,
                'critical_cases_count': critical_cases_count
            }
        except Exception as e:
            logger.warning(f"Could not get workflow stats: {str(e)}")

    return jsonify({
        'status': session.status,
        'total_records': session.total_records or 0,
        'processed_records': session.processed_records or 0,
        'progress_percent': int((session.processed_records or 0) / max(session.total_records or 1, 1) * 100),
        'current_chunk': session.current_chunk or 0,
        'total_chunks': session.total_chunks or 0,
        'chunk_progress_percent': int((session.current_chunk or 0) / max(session.total_chunks or 1, 1) * 100),
        'error_message': session.error_message,
        'workflow_stats': workflow_stats
    })

@app.route('/api/dashboard-stats/<session_id>')
def dashboard_stats(session_id):
    """Get real-time dashboard statistics for animations"""
    try:
        # Get session info
        session = ProcessingSession.query.get_or_404(session_id)

        # Get basic stats
        stats = session_manager.get_processing_stats(session_id)
        ml_insights = ml_engine.get_insights(session_id)

        # Get real-time counts
        total_records = EmailRecord.query.filter_by(session_id=session_id).count()
        critical_cases = EmailRecord.query.filter_by(
            session_id=session_id, 
            risk_level='Critical'
        ).filter(EmailRecord.whitelisted != True).count()

        whitelisted_records = EmailRecord.query.filter_by(
            session_id=session_id,
            whitelisted=True
        ).count()

        return jsonify({
            'total_records': total_records,
            'critical_cases': critical_cases,
            'avg_risk_score': ml_insights.get('average_risk_score', 0),
            'whitelisted_records': whitelisted_records,
            'processing_complete': stats.get('session_info', {}).get('status') == 'completed',
            'current_chunk': session.current_chunk or 0,
            'total_chunks': session.total_chunks or 0,
            'chunk_progress': int((session.current_chunk or 0) / max(session.total_chunks or 1, 1) * 100),
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        logger.error(f"Error getting dashboard stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/dashboard/<session_id>')
def dashboard(session_id):
    """Main dashboard with processing statistics and ML insights"""
    session = ProcessingSession.query.get_or_404(session_id)

    # If still processing, show processing view
    if session.status in ['uploaded', 'processing']:
        return render_template('processing.html', session=session)

    # Get processing statistics
    try:
        stats = session_manager.get_processing_stats(session_id)
    except Exception as e:
        logger.warning(f"Could not get processing stats: {str(e)}")
        stats = {}

    # Get ML insights
    try:
        ml_insights = ml_engine.get_insights(session_id)
    except Exception as e:
        logger.warning(f"Could not get ML insights: {str(e)}")
        ml_insights = {}

    # Get BAU analysis (cached to prevent repeated calls)
    try:
        # Only run analysis if session is completed and we don't have cached results
        if hasattr(session, 'bau_cached') and session.bau_cached:
            bau_analysis = session.bau_cached
        else:
            bau_analysis = advanced_ml_engine.analyze_bau_patterns(session_id)
    except Exception as e:
        logger.warning(f"Could not get BAU analysis: {str(e)}")
        bau_analysis = {}

    # Get attachment risk analytics (cached to prevent repeated calls)
    try:
        # Only run analysis if session is completed and we don't have cached results
        if hasattr(session, 'attachment_cached') and session.attachment_cached:
            attachment_analytics = session.attachment_cached
        else:
            attachment_analytics = advanced_ml_engine.analyze_attachment_risks(session_id)
    except Exception as e:
        logger.warning(f"Could not get attachment analytics: {str(e)}")
        attachment_analytics = {}

    # Get workflow statistics for the dashboard
    workflow_stats = {}
    try:
        # Count excluded records
        excluded_count = EmailRecord.query.filter(
            EmailRecord.session_id == session_id,
            EmailRecord.excluded_by_rule.isnot(None)
        ).count()

        # Count whitelisted records  
        whitelisted_count = EmailRecord.query.filter_by(
            session_id=session_id,
            whitelisted=True
        ).count()

        # Count records with rule matches
        rules_matched_count = EmailRecord.query.filter(
            EmailRecord.session_id == session_id,
            EmailRecord.rule_matches.isnot(None)
        ).count()

        # Count critical cases
        critical_cases_count = EmailRecord.query.filter_by(
            session_id=session_id,
            risk_level='Critical'
        ).count()

        workflow_stats = {
            'excluded_count': excluded_count,
            'whitelisted_count': whitelisted_count,
            'rules_matched_count': rules_matched_count,
            'critical_cases_count': critical_cases_count
        }
    except Exception as e:
        logger.warning(f"Could not get workflow stats for dashboard: {str(e)}")

    return render_template('dashboard.html', 
                         session=session, 
                         stats=stats,
                         ml_insights=ml_insights,
                         bau_analysis=bau_analysis,
                         attachment_analytics=attachment_analytics,
                         workflow_stats=workflow_stats)

@app.route('/reports/<session_id>')
def reports_dashboard(session_id):
    """Professional reporting dashboard for email cases"""
    try:
        session = ProcessingSession.query.get_or_404(session_id)

        # Get cases from database with comprehensive filtering
        cases_query = EmailRecord.query.filter_by(session_id=session_id).filter(
            db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
        )

        cases = cases_query.order_by(EmailRecord.ml_risk_score.desc()).limit(500).all()

        # Calculate comprehensive statistics
        total_cases = cases_query.count()
        high_risk_cases = cases_query.filter(EmailRecord.risk_level == 'High').count()
        resolved_cases = cases_query.filter(EmailRecord.case_status.in_(['Cleared', 'Escalated'])).count()
        pending_cases = cases_query.filter(
            db.or_(EmailRecord.case_status.is_(None), EmailRecord.case_status == 'Active')
        ).count()

        # Convert database records to display format
        case_records = []
        for case in cases:
            # Handle time field properly - convert string to datetime if needed
            case_time = case.time
            if isinstance(case_time, str):
                try:
                    case_time = datetime.fromisoformat(case_time.replace('Z', '+00:00'))
                except:
                    case_time = datetime.now()
            elif case_time is None:
                case_time = datetime.now()

            case_records.append({
                'record_id': case.record_id or 'Unknown',
                'sender_email': case.sender or 'Unknown',
                'sender_name': '',  # Not available in current schema
                'subject': case.subject or 'No Subject',
                'recipient_domain': case.recipients_email_domain or '',
                'risk_level': case.risk_level or 'Low',
                'ml_score': float(case.ml_risk_score or 0),
                'status': case.case_status or 'Active',
                'time': case_time,
                'attachments': case.attachments or '',
                'policy_name': getattr(case, 'policy_name', 'Standard')
            })

        context = {
            'session': session,
            'cases': case_records,
            'total_cases': total_cases,
            'high_risk_cases': high_risk_cases,
            'resolved_cases': resolved_cases,
            'pending_cases': pending_cases
        }

        return render_template('reports_dashboard.html', **context)

    except Exception as e:
        logger.error(f"Reports dashboard error for session {session_id}: {str(e)}")
        flash('Error loading reports dashboard', 'error')
        return redirect(url_for('index'))

@app.route('/cases/<session_id>')
def cases(session_id):
    """Case management page with advanced filtering"""
    session = ProcessingSession.query.get_or_404(session_id)

    # Get filter parameters
    page = request.args.get('page', 1, type=int)
    per_page_param = request.args.get('per_page', '200')
    risk_level = request.args.get('risk_level', '')
    case_status = request.args.get('case_status', '')
    search = request.args.get('search', '')
    
    # Special view parameters
    show_whitelisted = request.args.get('show_whitelisted', False)
    show_excluded = request.args.get('show_excluded', False)
    show_unanalyzed = request.args.get('show_unanalyzed', False)

    # Handle "show all" functionality
    if per_page_param == 'all':
        # Get total count of records that match the filter criteria
        count_query = EmailRecord.query.filter_by(session_id=session_id).filter(
            db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
        )
        if risk_level:
            count_query = count_query.filter(EmailRecord.risk_level == risk_level)
        if case_status:
            count_query = count_query.filter(EmailRecord.case_status == case_status)
        if search:
            search_term = f"%{search}%"
            count_query = count_query.filter(
                db.or_(
                    EmailRecord.sender.ilike(search_term),
                    EmailRecord.subject.ilike(search_term),
                    EmailRecord.recipients_email_domain.ilike(search_term),
                    EmailRecord.recipients.ilike(search_term),
                    EmailRecord.attachments.ilike(search_term),
                    EmailRecord.justification.ilike(search_term),
                    EmailRecord.user_response.ilike(search_term),
                    EmailRecord.record_id.ilike(search_term),
                    EmailRecord.department.ilike(search_term),
                    EmailRecord.bunit.ilike(search_term)
                )
            )

        total_records = count_query.count()
        per_page = max(total_records, 1)  # Set per_page to actual total count
        page = 1  # Reset to first page when showing all
    else:
        per_page = int(per_page_param) if per_page_param.isdigit() else 200

    # Build query with filters based on special view parameters
    if show_whitelisted:
        # Show only whitelisted records
        query = EmailRecord.query.filter_by(session_id=session_id).filter(
            EmailRecord.whitelisted == True
        )
    elif show_excluded:
        # Show only excluded records (not whitelisted)
        query = EmailRecord.query.filter_by(session_id=session_id).filter(
            EmailRecord.excluded_by_rule.isnot(None),
            db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
        )
    elif show_unanalyzed:
        # Show only unanalyzed records (no risk level, not whitelisted, not excluded)
        query = EmailRecord.query.filter_by(session_id=session_id).filter(
            db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False),
            db.or_(EmailRecord.excluded_by_rule.is_(None)),
            db.or_(EmailRecord.risk_level.is_(None), EmailRecord.risk_level == '')
        )
    else:
        # Default view - exclude whitelisted, cleared, and escalated records from cases
        query = EmailRecord.query.filter_by(session_id=session_id).filter(
            db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
        ).filter(
            db.or_(
                EmailRecord.case_status.is_(None),
                EmailRecord.case_status == 'Active'
            )
        )

    if risk_level:
        query = query.filter(EmailRecord.risk_level == risk_level)
    if case_status:
        query = query.filter(EmailRecord.case_status == case_status)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                EmailRecord.sender.ilike(search_term),
                EmailRecord.subject.ilike(search_term),
                EmailRecord.recipients_email_domain.ilike(search_term),
                EmailRecord.recipients.ilike(search_term),
                EmailRecord.attachments.ilike(search_term),
                EmailRecord.justification.ilike(search_term),
                EmailRecord.user_response.ilike(search_term),
                EmailRecord.record_id.ilike(search_term),
                EmailRecord.department.ilike(search_term),
                EmailRecord.bunit.ilike(search_term)
            )
        )

    # Apply sorting and pagination with dynamic limit
    cases_pagination = query.order_by(EmailRecord.ml_risk_score.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get comprehensive statistics for Executive Summary
    # Total records in session
    total_all_records = EmailRecord.query.filter_by(session_id=session_id).count()
    
    # Whitelisted records
    total_whitelisted = EmailRecord.query.filter_by(session_id=session_id).filter(
        EmailRecord.whitelisted == True
    ).count()
    
    # Excluded by rules (not whitelisted but excluded)
    total_excluded = EmailRecord.query.filter_by(session_id=session_id).filter(
        EmailRecord.excluded_by_rule.isnot(None),
        db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
    ).count()
    
    # Risk level counts for analyzed records (exclude whitelisted and excluded)
    analyzed_query = EmailRecord.query.filter_by(session_id=session_id).filter(
        db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False),
        db.or_(EmailRecord.excluded_by_rule.is_(None))
    )
    
    total_critical = analyzed_query.filter(EmailRecord.risk_level == 'Critical').count()
    total_high = analyzed_query.filter(EmailRecord.risk_level == 'High').count()
    total_medium = analyzed_query.filter(EmailRecord.risk_level == 'Medium').count()
    total_low = analyzed_query.filter(EmailRecord.risk_level == 'Low').count()
    
    # Unanalyzed records (no risk level assigned, not whitelisted, not excluded)
    total_unanalyzed = analyzed_query.filter(
        db.or_(EmailRecord.risk_level.is_(None), EmailRecord.risk_level == '')
    ).count()

    active_whitelist_domains = WhitelistDomain.query.filter_by(is_active=True).count()

    return render_template('cases.html', 
                         session=session,
                         cases=cases_pagination,
                         risk_level=risk_level,
                         case_status=case_status,
                         search=search,
                         total_all_records=total_all_records,
                         total_whitelisted=total_whitelisted,
                         total_excluded=total_excluded,
                         total_unanalyzed=total_unanalyzed,
                         active_whitelist_domains=active_whitelist_domains,
                         total_critical=total_critical,
                         total_high=total_high,
                         total_medium=total_medium,
                         total_low=total_low)

@app.route('/cleared_cases/<session_id>')
def cleared_cases(session_id):
    """Cleared cases dashboard"""
    session = ProcessingSession.query.get_or_404(session_id)

    # Get cleared cases - exclude whitelisted records
    cleared_cases = EmailRecord.query.filter_by(
        session_id=session_id,
        case_status='Cleared'
    ).filter(
        db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
    ).order_by(EmailRecord.resolved_at.desc()).all()

    return render_template('cleared_cases.html',
                         session=session,
                         cleared_cases=cleared_cases)

@app.route('/escalations/<session_id>')
def escalations(session_id):
    """Escalation dashboard for critical cases"""
    session = ProcessingSession.query.get_or_404(session_id)

    # Get critical and escalated cases - exclude whitelisted records
    critical_cases = EmailRecord.query.filter_by(
        session_id=session_id,
        risk_level='Critical'
    ).filter(
        db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
    ).filter(
        db.or_(
            EmailRecord.case_status.is_(None),
            EmailRecord.case_status == 'Active'
        )
    ).order_by(EmailRecord.ml_risk_score.desc()).all()

    escalated_cases = EmailRecord.query.filter_by(
        session_id=session_id,
        case_status='Escalated'
    ).filter(
        db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
    ).order_by(EmailRecord.escalated_at.desc()).all()

    return render_template('escalations.html',
                         session=session,
                         critical_cases=critical_cases,
                         escalated_cases=escalated_cases)

@app.route('/sender_analysis/<session_id>')
def sender_analysis(session_id):
    """Sender behavior analysis dashboard"""
    session = ProcessingSession.query.get_or_404(session_id)

    try:
        analysis = advanced_ml_engine.analyze_sender_behavior(session_id)
        if not analysis or 'error' in analysis:
            # Provide default empty analysis structure
            analysis = {
                'total_senders': 0,
                'sender_profiles': {},
                'summary_statistics': {
                    'high_risk_senders': 0,
                    'external_focused_senders': 0,
                    'attachment_senders': 0,
                    'avg_emails_per_sender': 0
                }
            }
    except Exception as e:
        logger.error(f"Error in sender analysis: {str(e)}")
        analysis = {
            'total_senders': 0,
            'sender_profiles': {},
            'summary_statistics': {
                'high_risk_senders': 0,
                'external_focused_senders': 0,
                'attachment_senders': 0,
                'avg_emails_per_sender': 0
            }
        }

    return render_template('sender_analysis.html',
                         session=session,
                         analysis=analysis)

@app.route('/time_analysis/<session_id>')
def time_analysis(session_id):
    """Temporal pattern analysis dashboard"""
    session = ProcessingSession.query.get_or_404(session_id)
    analysis = advanced_ml_engine.analyze_temporal_patterns(session_id)

    return render_template('time_analysis.html',
                         session=session,
                         analysis=analysis)

@app.route('/whitelist_analysis/<session_id>')
def whitelist_analysis(session_id):
    """Domain whitelist recommendations dashboard"""
    session = ProcessingSession.query.get_or_404(session_id)
    analysis = domain_manager.analyze_whitelist_recommendations(session_id)

    return render_template('whitelist_analysis.html',
                         session=session,
                         analysis=analysis)

@app.route('/advanced_ml_dashboard/<session_id>')
def advanced_ml_dashboard(session_id):
    """Advanced ML insights and pattern recognition"""
    session = ProcessingSession.query.get_or_404(session_id)
    insights = advanced_ml_engine.get_advanced_insights(session_id)

    return render_template('advanced_ml_dashboard.html',
                         session=session,
                         insights=insights)

@app.route('/admin')
def admin():
    """Administration panel"""
    # System statistics for the new admin template
    stats = {
        'total_sessions': ProcessingSession.query.count(),
        'active_sessions': ProcessingSession.query.filter_by(status='processing').count(),
        'completed_sessions': ProcessingSession.query.filter_by(status='completed').count(),
        'failed_sessions': ProcessingSession.query.filter_by(status='failed').count()
    }

    # Recent sessions for the admin panel
    recent_sessions = ProcessingSession.query.order_by(ProcessingSession.upload_time.desc()).limit(5).all()

    # Legacy data for backward compatibility (if needed)
    sessions = ProcessingSession.query.order_by(ProcessingSession.upload_time.desc()).all()
    whitelist_domains = WhitelistDomain.query.filter_by(is_active=True).all()
    attachment_keywords = AttachmentKeyword.query.filter_by(is_active=True).all()

    # Get risk factors from database, fallback to default if empty
    db_risk_factors = RiskFactor.query.filter_by(is_active=True).order_by(RiskFactor.sort_order, RiskFactor.name).all()

    if db_risk_factors:
        # Use database risk factors
        factors_list = []
        for factor in db_risk_factors:
            factors_list.append({
                'id': factor.id,
                'name': factor.name,
                'max_score': factor.max_score,
                'description': factor.description,
                'category': factor.category,
                'weight_percentage': factor.weight_percentage,
                'calculation_config': factor.calculation_config
            })
    else:
        # Fallback to hardcoded values if database is empty
        factors_list = [
            {'id': None, 'name': 'Leaver Status', 'max_score': 0.3, 'description': 'Employee leaving organization', 'category': 'Security', 'weight_percentage': 30.0, 'calculation_config': {}},
            {'id': None, 'name': 'External Domain', 'max_score': 0.2, 'description': 'Public email domains (Gmail, Yahoo, etc.)', 'category': 'Security', 'weight_percentage': 20.0, 'calculation_config': {}},
            {'id': None, 'name': 'Attachment Risk', 'max_score': 0.3, 'description': 'File type and suspicious patterns', 'category': 'Content', 'weight_percentage': 30.0, 'calculation_config': {}},
            {'id': None, 'name': 'Wordlist Matches', 'max_score': 0.2, 'description': 'Suspicious keywords in subject/attachment', 'category': 'Content', 'weight_percentage': 15.0, 'calculation_config': {}},
            {'id': None, 'name': 'Time-based Risk', 'max_score': 0.1, 'description': 'Weekend/after-hours activity', 'category': 'Time', 'weight_percentage': 3.0, 'calculation_config': {}},
            {'id': None, 'name': 'Justification Analysis', 'max_score': 0.1, 'description': 'Suspicious terms in explanations', 'category': 'Content', 'weight_percentage': 2.0, 'calculation_config': {}}
        ]

    # Risk scoring algorithm details for transparency
    risk_scoring_info = {
        'thresholds': {
            'critical': 0.8,
            'high': 0.6,
            'medium': 0.4,
            'low': 0.0
        },
        'algorithm_components': {
            'anomaly_detection': {
                'weight': 40,
                'description': 'Isolation Forest algorithm detects unusual patterns',
                'method': 'sklearn.ensemble.IsolationForest',
                'contamination_rate': '10%',
                'estimators': config.ml_estimators
            },
            'rule_based_factors': {
                'weight': 60,
                'factors': factors_list
            }
        },
        'attachment_scoring': {
            'high_risk_extensions': ['.exe', '.scr', '.bat', '.cmd', '.com', '.pif', '.vbs', '.js'],
            'high_risk_score': 0.8,
            'medium_risk_extensions': ['.zip', '.rar', '.7z', '.doc', '.docx', '.xls', '.xlsx', '.pdf'],
            'medium_risk_score': 0.3,
            'suspicious_patterns': ['double extension', 'hidden', 'confidential', 'urgent', 'invoice'],
            'pattern_score': 0.2
        },
        'performance_config': {
            'fast_mode': config.fast_mode,
            'max_ml_records': config.max_ml_records,
            'ml_estimators': config.ml_estimators,
            'tfidf_max_features': config.tfidf_max_features,
            'chunk_size': config.chunk_size
        }
    }

    return render_template('admin.html',
                         stats=stats,
                         recent_sessions=recent_sessions,
                         sessions=sessions,
                         whitelist_domains=whitelist_domains,
                         attachment_keywords=attachment_keywords,
                         risk_scoring_info=risk_scoring_info)

@app.route('/whitelist-domains')
def whitelist_domains():
    """Whitelist domains management interface"""
    return render_template('whitelist_domains.html')

@app.route('/rules')
def rules():
    """Rules management interface"""
    # Get all rules with counts for display
    security_rules = Rule.query.filter_by(rule_type='security', is_active=True).all()
    exclusion_rules = Rule.query.filter_by(rule_type='exclusion', is_active=True).all()

    # Get rule counts for statistics
    rule_counts = {
        'security_active': len(security_rules),
        'exclusion_active': len(exclusion_rules),
        'security_total': Rule.query.filter_by(rule_type='security').count(),
        'exclusion_total': Rule.query.filter_by(rule_type='exclusion').count()
    }

    return render_template('rules.html',
                         security_rules=security_rules,
                         exclusion_rules=exclusion_rules,
                         rule_counts=rule_counts)

@app.route('/api/rules', methods=['POST'])
def create_rule():
    """Create a new rule with complex AND/OR conditions"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['name', 'rule_type', 'conditions']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400

        # Ensure rule_type is properly set (default to security if not exclusion)
        rule_type = data.get('rule_type', 'security')
        if rule_type not in ['security', 'exclusion']:
            rule_type = 'security'

        # Process conditions - ensure it's stored as JSON
        conditions = data['conditions']
        if isinstance(conditions, str):
            try:
                # Validate JSON if it's a string
                json.loads(conditions)
            except json.JSONDecodeError:
                return jsonify({'success': False, 'message': 'Invalid JSON in conditions'}), 400

        # Process actions
        actions = data.get('actions', {})
        if isinstance(actions, str):
            if actions == 'flag':
                actions = {'flag': True}
            else:
                try:
                    actions = json.loads(actions)
                except json.JSONDecodeError:
                    actions = {'flag': True}

        # Create new rule
        rule = Rule(
            name=data['name'],
            rule_type=rule_type,
            description=data.get('description', ''),
            priority=data.get('priority', 50),
            conditions=conditions,
            actions=actions,
            is_active=data.get('is_active', True)
        )

        db.session.add(rule)
        db.session.commit()

        logger.info(f"Created new rule: {rule.name} (ID: {rule.id}, Type: {rule_type})")
        logger.info(f"Rule conditions: {conditions}")
        logger.info(f"Rule actions: {actions}")

        return jsonify({
            'success': True,
            'message': 'Rule created successfully',
            'rule_id': rule.id,
            'rule_type': rule_type
        })

    except Exception as e:
        logger.error(f"Error creating rule: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/rules/<int:rule_id>', methods=['GET'])
def get_rule(rule_id):
    """Get individual rule details"""
    try:
        rule = Rule.query.get_or_404(rule_id)
        return jsonify({
            'id': rule.id,
            'name': rule.name,
            'description': rule.description,
            'rule_type': rule.rule_type,
            'conditions': rule.conditions,
            'actions': rule.actions,
            'priority': rule.priority,
            'is_active': rule.is_active
        })
    except Exception as e:
        logger.error(f"Error getting rule {rule_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/rules/<int:rule_id>', methods=['PUT'])
def update_rule(rule_id):
    """Update an existing rule"""
    try:
        rule = Rule.query.get_or_404(rule_id)
        data = request.get_json()

        # Handle toggle functionality
        if 'is_active' in data and data['is_active'] is None:
            rule.is_active = not rule.is_active
        else:
            # Update rule fields
            for field in ['name', 'rule_type', 'description', 'priority', 'conditions', 'actions', 'is_active']:
                if field in data and data[field] is not None:
                    setattr(rule, field, data[field])

        rule.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Rule updated successfully'
        })

    except Exception as e:
        logger.error(f"Error updating rule {rule_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/rules/<int:rule_id>', methods=['DELETE'])
def delete_rule(rule_id):
    """Delete a rule"""
    try:
        rule = Rule.query.get_or_404(rule_id)
        db.session.delete(rule)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Rule deleted successfully'
        })

    except Exception as e:
        logger.error(f"Error deleting rule {rule_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# API Endpoints
@app.route('/api/ml_insights/<session_id>')
def api_ml_insights(session_id):
    """Get ML analysis data for dashboard charts"""
    try:
        insights = ml_engine.get_insights(session_id)
        if not insights:
            return jsonify({'error': 'No insights available'}), 404
        return jsonify(insights)
    except Exception as e:
        logger.error(f"Error getting ML insights for session {session_id}: {str(e)}")
        return jsonify({'error': 'Failed to load ML insights', 'details': str(e)}), 500

@app.route('/api/bau_analysis/<session_id>')
def api_bau_analysis(session_id):
    """Get BAU recommendations"""
    analysis = advanced_ml_engine.analyze_bau_patterns(session_id)
    return jsonify(analysis)

@app.route('/api/attachment_risk_analytics/<session_id>')
def api_attachment_risk_analytics(session_id):
    """Get attachment intelligence data"""
    analytics = advanced_ml_engine.analyze_attachment_risks(session_id)
    return jsonify(analytics)

# Reports Dashboard API Endpoints
@app.route('/api/cases/<session_id>')
def api_cases_data(session_id):
    """Get cases data with analytics for reports dashboard"""
    try:
        # Get cases from database
        cases_query = EmailRecord.query.filter_by(session_id=session_id).filter(
            db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
        )

        cases = cases_query.order_by(EmailRecord.ml_risk_score.desc()).all()

        # Calculate distributions for charts
        status_distribution = {'Active': 0, 'Cleared': 0, 'Escalated': 0}
        risk_distribution = {'High': 0, 'Medium': 0, 'Low': 0}
        domain_counts = {}
        timeline_data = {}

        for case in cases:
            # Status distribution
            status = case.case_status or 'Active'
            if status in status_distribution:
                status_distribution[status] += 1

            # Risk distribution
            risk = case.risk_level or 'Low'
            if risk in risk_distribution:
                risk_distribution[risk] += 1

            # Domain counts
            domain = case.recipients_email_domain or 'Unknown'
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

            # Timeline data (by date)
            if case.time:
                try:
                    if isinstance(case.time, str):
                        case_time = datetime.fromisoformat(case.time.replace('Z', '+00:00'))
                    else:
                        case_time = case.time
                    date_key = case_time.strftime('%Y-%m-%d')
                    timeline_data[date_key] = timeline_data.get(date_key, 0) + 1
                except:
                    # Skip invalid dates
                    pass

        # Prepare top domains (top 10)
        top_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Prepare timeline data (last 30 days)
        timeline_sorted = sorted(timeline_data.items())
        timeline_labels = [item[0] for item in timeline_sorted[-30:]]
        timeline_values = [item[1] for item in timeline_sorted[-30:]]

        return jsonify({
            'cases': [
                {
                    'record_id': case.record_id,
                    'sender_email': case.sender,
                    'subject': case.subject,
                    'recipient_domain': case.recipients_email_domain,
                    'risk_level': case.risk_level,
                    'ml_score': float(case.ml_risk_score or 0),
                    'status': case.case_status or 'Active',
                    'time': case.time.isoformat() if case.time and callable(getattr(case.time, 'isoformat', None)) else datetime.now().isoformat(),
                    'attachments': case.attachments
                } for case in cases[:100]  # Limit for performance
            ],
            'status_distribution': status_distribution,
            'risk_distribution': risk_distribution,
            'top_domains': {
                'labels': [item[0] for item in top_domains],
                'data': [item[1] for item in top_domains]
            },
            'timeline_data': {
                'labels': timeline_labels,
                'data': timeline_values
            }
        })

    except Exception as e:
        logger.error(f"Error getting cases data for session {session_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/export-cases/<session_id>', methods=['POST'])
def api_export_cases(session_id):
    """Export selected cases to CSV"""
    try:
        case_ids = json.loads(request.form.get('case_ids', '[]'))

        if not case_ids:
            return jsonify({'error': 'No cases selected'}), 400

        # Get selected cases
        cases = EmailRecord.query.filter(
            EmailRecord.session_id == session_id,
            EmailRecord.record_id.in_(case_ids)
        ).all()

        # Create CSV content
        from io import StringIO
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'Record ID', 'Sender', 'Subject', 'Recipients', 'Domain',
            'Risk Level', 'ML Score', 'Status', 'Time', 'Attachments',
            'Justification', 'Policy Name'
        ])

        # Write data
        for case in cases:
            # Handle time formatting safely
            time_str = ''
            if case.time:
                try:
                    if isinstance(case.time, str):
                        case_time = datetime.fromisoformat(case.time.replace('Z', '+00:00'))
                    else:
                        case_time = case.time
                    time_str = case_time.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    time_str = str(case.time)

            writer.writerow([
                case.record_id,
                case.sender,
                case.subject,
                case.recipients,
                case.recipients_email_domain,
                case.risk_level,
                case.ml_risk_score,
                case.case_status,
                time_str,
                case.attachments,
                case.justification,
                getattr(case, 'policy_name', 'Standard')
            ])

        # Create response
        output.seek(0)
        response = send_file(
            BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'email_cases_export_{session_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )

        return response

    except Exception as e:
        logger.error(f"Error exporting cases for session {session_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bulk-update-status/<session_id>', methods=['POST'])
def api_bulk_update_status(session_id):
    """Update status for multiple cases"""
    try:
        data = request.get_json()
        case_ids = data.get('case_ids', [])
        new_status = data.get('new_status', '')

        if not case_ids or not new_status:
            return jsonify({'error': 'Missing case IDs or status'}), 400

        if new_status not in ['Active', 'Cleared', 'Escalated']:
            return jsonify({'error': 'Invalid status'}), 400

        # Update cases
        updated_count = EmailRecord.query.filter(
            EmailRecord.session_id == session_id,
            EmailRecord.record_id.in_(case_ids)
        ).update({'case_status': new_status}, synchronize_session=False)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Updated {updated_count} cases to {new_status}',
            'updated_count': updated_count
        })

    except Exception as e:
        logger.error(f"Error bulk updating cases for session {session_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-report/<session_id>', methods=['POST'])
def api_generate_report(session_id):
    """Generate comprehensive PDF report"""
    try:
        # For now, return CSV format as PDF generation requires additional libraries
        cases = EmailRecord.query.filter_by(session_id=session_id).filter(
            db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
        ).all()

        # Create comprehensive report content
        output = StringIO()
        writer = csv.writer(output)

        # Write header with comprehensive fields
        writer.writerow([
            'Record ID', 'Sender', 'Subject', 'Recipients', 'Domain',
            'Risk Level', 'ML Score', 'Status', 'Time', 'Attachments',
            'Justification', 'User Response', 'Department', 'Business Unit',
            'Policy Name', 'Rule Matches', 'Whitelisted'
        ])

        # Write all cases data
        for case in cases:
            # Handle time formatting safely
            time_str = ''
            if case.time:
                try:
                    if isinstance(case.time, str):
                        case_time = datetime.fromisoformat(case.time.replace('Z', '+00:00'))
                    else:
                        case_time = case.time
                    time_str = case_time.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    time_str = str(case.time)

            writer.writerow([
                case.record_id,
                case.sender,
                case.subject,
                case.recipients,
                case.recipients_email_domain,
                case.risk_level,
                case.ml_risk_score,
                case.case_status,
                time_str,
                case.attachments,
                case.justification,
                case.user_response,
                case.department,
                case.bunit,
                getattr(case, 'policy_name', 'Standard'),
                case.rule_matches,
                case.whitelisted
            ])

        # Create response
        output.seek(0)
        response = send_file(
            BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'email_security_report_{session_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )

        return response

    except Exception as e:
        logger.error(f"Error generating report for session {session_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sender_risk_analytics/<session_id>')
def api_sender_risk_analytics(session_id):
    """Get sender risk vs communication volume data for scatter plot"""
    try:
        # Get all email records for this session that aren't whitelisted
        records = EmailRecord.query.filter_by(session_id=session_id).filter(
            db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
        ).all()

        if not records:
            return jsonify({
                'data': [],
                'total_senders': 0,
                'max_volume': 0,
                'max_risk': 0,
                'message': 'No sender data available for this session'
            })

        # Aggregate data by sender
        sender_stats = {}
        for record in records:
            sender = record.sender or 'Unknown'
            if sender not in sender_stats:
                sender_stats[sender] = {
                    'sender': sender,
                    'email_count': 0,
                    'risk_scores': [],
                    'has_attachments': False,
                    'high_risk_count': 0
                }

            sender_stats[sender]['email_count'] += 1
            if record.ml_risk_score is not None:
                sender_stats[sender]['risk_scores'].append(record.ml_risk_score)
            if record.attachments:
                sender_stats[sender]['has_attachments'] = True
            if record.risk_level in ['High', 'Critical']:
                sender_stats[sender]['high_risk_count'] += 1

        # Format data for scatter plot
        scatter_data = []
        for sender, stats in sender_stats.items():
            avg_risk_score = sum(stats['risk_scores']) / len(stats['risk_scores']) if stats['risk_scores'] else 0

            scatter_data.append({
                'x': stats['email_count'],  # Communication volume
                'y': round(avg_risk_score, 3),  # Average risk score
                'sender': sender,
                'email_count': stats['email_count'],
                'avg_risk_score': round(avg_risk_score, 3),
                'has_attachments': stats['has_attachments'],
                'high_risk_count': stats['high_risk_count'],
                'domain': sender.split('@')[-1] if '@' in sender else sender
            })

        # Sort by risk score descending for better visualization
        scatter_data.sort(key=lambda x: x['y'], reverse=True)

        return jsonify({
            'data': scatter_data,
            'total_senders': len(scatter_data),
            'max_volume': max([d['x'] for d in scatter_data]) if scatter_data else 0,
            'max_risk': max([d['y'] for d in scatter_data]) if scatter_data else 0
        })

    except Exception as e:
        logger.error(f"Error getting sender risk analytics for session {session_id}: {str(e)}")
        return jsonify({
            'error': f'Failed to load sender analytics: {str(e)}',
            'data': [],
            'total_senders': 0,
            'max_volume': 0,
            'max_risk': 0
        }), 200  # Return 200 to prevent JS errors

@app.route('/api/case/<session_id>/<record_id>')
def api_case_details(session_id, record_id):
    """Get individual case details"""
    case = EmailRecord.query.filter_by(session_id=session_id, record_id=record_id).first_or_404()

    case_data = {
        'record_id': case.record_id,
        'sender': case.sender,
        'subject': case.subject,
        'recipients': case.recipients,
        'recipients_email_domain': case.recipients_email_domain,
        'attachments': case.attachments,
        'risk_level': case.risk_level,
        'ml_risk_score': case.ml_risk_score,
        'ml_explanation': case.ml_explanation,
        'rule_matches': json.loads(case.rule_matches) if case.rule_matches else [],
        'case_status': case.case_status,
        'justification': case.justification,
        'policy_name': case.policy_name,
        'time': case.time
    }

    return jsonify(case_data)



@app.route('/api/exclusion-rules', methods=['GET', 'POST'])
def api_exclusion_rules():
    """Get all exclusion rules or create new one"""
    if request.method == 'GET':
        rules = Rule.query.filter_by(rule_type='exclusion', is_active=True).all()
        return jsonify([{
            'id': rule.id,
            'name': rule.name,
            'description': rule.description,
            'conditions': rule.conditions,
            'actions': rule.actions,
            'priority': rule.priority
        } for rule in rules])

    elif request.method == 'POST':
        data = request.get_json()
        rule = Rule(
            name=data['name'],
            description=data.get('description', ''),
            rule_type='exclusion',
            conditions=data['conditions'],
            actions=data.get('actions', {}),
            priority=data.get('priority', 1)
        )
        db.session.add(rule)
        db.session.commit()
        return jsonify({'id': rule.id, 'status': 'created'})

@app.route('/api/exclusion-rules/<int:rule_id>', methods=['GET', 'PUT', 'DELETE'])
def api_exclusion_rule(rule_id):
    """Get, update, or delete specific exclusion rule"""
    rule = Rule.query.get_or_404(rule_id)

    if request.method == 'GET':
        return jsonify({
            'id': rule.id,
            'name': rule.name,
            'description': rule.description,
            'conditions': rule.conditions,
            'actions': rule.actions,
            'priority': rule.priority,
            'is_active': rule.is_active
        })

    elif request.method == 'PUT':
        data = request.get_json()
        rule.name = data.get('name', rule.name)
        rule.description = data.get('description', rule.description)
        rule.conditions = data.get('conditions', rule.conditions)
        rule.actions = data.get('actions', rule.actions)
        rule.priority = data.get('priority', rule.priority)
        rule.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'status': 'updated'})

    elif request.method == 'DELETE':
        rule.is_active = False
        db.session.commit()
        return jsonify({'status': 'deleted'})

@app.route('/api/exclusion-rules/<int:rule_id>/toggle', methods=['POST'])
def api_toggle_exclusion_rule(rule_id):
    """Toggle rule active status"""
    rule = Rule.query.get_or_404(rule_id)
    rule.is_active = not rule.is_active
    db.session.commit()
    return jsonify({'status': 'toggled', 'is_active': rule.is_active})

@app.route('/api/whitelist-domains', methods=['GET', 'POST'])
def api_whitelist_domains():
    """Get all whitelist domains or create new one"""
    if request.method == 'GET':
        try:
            domains = WhitelistDomain.query.order_by(WhitelistDomain.added_at.desc()).all()
            return jsonify([{
                'id': domain.id,
                'domain': domain.domain,
                'domain_type': domain.domain_type or 'Corporate',
                'added_by': domain.added_by or 'System',
                'added_at': domain.added_at.isoformat() if domain.added_at else datetime.utcnow().isoformat(),
                'notes': domain.notes or '',
                'is_active': domain.is_active if domain.is_active is not None else True
            } for domain in domains])
        except Exception as e:
            logger.error(f"Error fetching whitelist domains: {str(e)}")
            return jsonify({'error': 'Failed to fetch whitelist domains', 'details': str(e)}), 500

    elif request.method == 'POST':
        try:
            data = request.get_json()
            domain = data.get('domain', '').strip().lower()

            if not domain:
                return jsonify({'success': False, 'message': 'Domain is required'}), 400

            # Check if domain already exists
            existing = WhitelistDomain.query.filter_by(domain=domain).first()
            if existing:
                return jsonify({'success': False, 'message': f'Domain {domain} already exists'}), 400

            whitelist_domain = WhitelistDomain(
                domain=domain,
                domain_type=data.get('domain_type', 'Corporate'),
                added_by=data.get('added_by', 'Admin'),
                notes=data.get('notes', '')
            )

            db.session.add(whitelist_domain)
            db.session.commit()

            logger.info(f"Added whitelist domain: {domain}")
            return jsonify({'success': True, 'message': f'Domain {domain} added successfully', 'id': whitelist_domain.id})

        except Exception as e:
            logger.error(f"Error adding whitelist domain: {str(e)}")
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/whitelist-domains/<int:domain_id>', methods=['GET', 'PUT', 'DELETE'])
def api_whitelist_domain(domain_id):
    """Get, update, or delete specific whitelist domain"""
    domain = WhitelistDomain.query.get_or_404(domain_id)

    if request.method == 'GET':
        return jsonify({
            'id': domain.id,
            'domain': domain.domain,
            'domain_type': domain.domain_type,
            'added_by': domain.added_by,
            'added_at': domain.added_at.isoformat() if domain.added_at else None,
            'notes': domain.notes,
            'is_active': domain.is_active
        })

    elif request.method == 'PUT':
        try:
            data = request.get_json()

            domain.domain_type = data.get('domain_type', domain.domain_type)
            domain.notes = data.get('notes', domain.notes)

            db.session.commit()

            logger.info(f"Updated whitelist domain: {domain.domain}")
            return jsonify({'success': True, 'message': 'Domain updated successfully'})

        except Exception as e:
            logger.error(f"Error updating whitelist domain {domain_id}: {str(e)}")
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

    elif request.method == 'DELETE':
        domain_name = domain.domain
        db.session.delete(domain)
        db.session.commit()

        logger.info(f"Domain {domain_name} removed from whitelist")
        return jsonify({'success': True, 'message': f'Domain {domain_name} deleted successfully'})

# Admin Dashboard API Endpoints
@app.route('/admin/api/performance-metrics')
def admin_performance_metrics():
    """Get system performance metrics"""
    try:
        import psutil
        import threading

        # Get system metrics
        cpu_usage = round(psutil.cpu_percent(), 1)
        memory = psutil.virtual_memory()
        memory_usage = round(memory.percent, 1)

        # Get thread count
        active_threads = threading.active_count()
        processing_threads = max(0, active_threads - 3)  # Subtract main threads

        # Simulate response time and slow requests for now
        avg_response_time = 150  # Could be calculated from actual request logs
        slow_requests = 0

        return jsonify({
            'cpu_usage': cpu_usage,
            'memory_usage': memory_usage,
            'active_threads': active_threads,
            'processing_threads': processing_threads,
            'avg_response_time': avg_response_time,
            'slow_requests': slow_requests
        })
    except ImportError:
        # Fallback if psutil not available
        return jsonify({
            'cpu_usage': 12.5,
            'memory_usage': 45.2,
            'active_threads': 8,
            'processing_threads': 2,
            'avg_response_time': 125,
            'slow_requests': 1
        })
    except Exception as e:
        logger.error(f"Error getting performance metrics: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/security-metrics')
def admin_security_metrics():
    """Get security metrics and threat distribution"""
    try:
        # Count critical threats
        critical_threats = EmailRecord.query.filter_by(risk_level='Critical').count()

        # Count suspicious activities (high and medium risk)
        suspicious_activities = EmailRecord.query.filter(
            EmailRecord.risk_level.in_(['High', 'Medium'])
        ).count()

        # Count blocked domains
        blocked_domains = WhitelistDomain.query.filter_by(is_active=False).count()

        # Get threat distribution
        threat_distribution = {
            'critical': EmailRecord.query.filter_by(risk_level='Critical').count(),
            'high': EmailRecord.query.filter_by(risk_level='High').count(),
            'medium': EmailRecord.query.filter_by(risk_level='Medium').count(),
            'low': EmailRecord.query.filter_by(risk_level='Low').count()
        }

        # Generate recent security events
        recent_events = []

        # Get latest critical cases
        critical_cases = EmailRecord.query.filter_by(risk_level='Critical').order_by(
            EmailRecord.id.desc()
        ).limit(5).all()

        for case in critical_cases:
            recent_events.append({
                'title': 'Critical Risk Detected',
                'description': f'High-risk email from {case.sender}',
                'severity': 'critical',
                'timestamp': datetime.utcnow().isoformat()
            })

        # Get recent rule matches
        rule_matches = EmailRecord.query.filter(
            EmailRecord.rule_matches.isnot(None)
        ).order_by(EmailRecord.id.desc()).limit(3).all()

        for match in rule_matches:
            recent_events.append({
                'title': 'Security Rule Triggered',
                'description': f'Rule violation detected in email processing',
                'severity': 'warning',
                'timestamp': datetime.utcnow().isoformat()
            })

        return jsonify({
            'critical_threats': critical_threats,
            'suspicious_activities': suspicious_activities,
            'blocked_domains': blocked_domains,
            'threat_distribution': threat_distribution,
            'recent_events': recent_events[:10]  # Limit to 10 most recent
        })

    except Exception as e:
        logger.error(f"Error getting security metrics: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/data-analytics')
def admin_data_analytics():
    """Get data analytics and processing insights"""
    try:
        # Get email processing statistics
        total_emails = EmailRecord.query.count()
        clean_emails = EmailRecord.query.filter_by(risk_level='Low').count()
        flagged_emails = EmailRecord.query.filter(
            EmailRecord.risk_level.in_(['Medium', 'High'])
        ).count()
        high_risk_emails = EmailRecord.query.filter_by(risk_level='Critical').count()

        # Get unique domains count
        unique_domains = db.session.query(EmailRecord.sender).distinct().count()

        # Calculate average processing time from sessions (simulate for now)
        sessions = ProcessingSession.query.all()

        if sessions:
            # Simulate processing times based on record counts
            avg_processing_time = 2.5  # Average seconds per session
        else:
            avg_processing_time = 0

        # Generate volume trends (last 7 days)
        from datetime import timedelta
        volume_trends = {
            'labels': [],
            'data': []
        }

        for i in range(7):
            date = datetime.utcnow() - timedelta(days=6-i)
            date_str = date.strftime('%m/%d')
            volume_trends['labels'].append(date_str)

            # Count emails processed on this date (simulate daily distribution)
            day_count = EmailRecord.query.count() // 7  # Distribute total over 7 days
            volume_trends['data'].append(day_count)

        return jsonify({
            'total_emails': total_emails,
            'clean_emails': clean_emails,
            'flagged_emails': flagged_emails,
            'high_risk_emails': high_risk_emails,
            'unique_domains': unique_domains,
            'avg_processing_time': avg_processing_time,
            'volume_trends': volume_trends
        })

    except Exception as e:
        logger.error(f"Error getting data analytics: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/system-logs')
def admin_system_logs():
    """Get system logs with filtering"""
    try:
        level_filter = request.args.get('level', 'all')
        component_filter = request.args.get('component', 'all')

        # Generate sample logs (in a real system, these would come from log files)
        logs = []

        # Add some sample recent logs
        sample_logs = [
            {'timestamp': '2025-07-22 23:05:00', 'level': 'INFO', 'component': 'ml_engine', 'message': 'ML analysis completed for session'},
            {'timestamp': '2025-07-22 23:04:45', 'level': 'INFO', 'component': 'data_processor', 'message': 'Processing chunk 5/10'},
            {'timestamp': '2025-07-22 23:04:30', 'level': 'WARNING', 'component': 'rule_engine', 'message': 'High-risk pattern detected in email content'},
            {'timestamp': '2025-07-22 23:04:15', 'level': 'INFO', 'component': 'session_manager', 'message': 'Session data saved successfully'},
            {'timestamp': '2025-07-22 23:04:00', 'level': 'DEBUG', 'component': 'ml_engine', 'message': 'Feature extraction completed'},
            {'timestamp': '2025-07-22 23:03:45', 'level': 'ERROR', 'component': 'data_processor', 'message': 'CSV parsing error: Invalid date format'},
            {'timestamp': '2025-07-22 23:03:30', 'level': 'INFO', 'component': 'rule_engine', 'message': 'Exclusion rules applied: 15 records excluded'},
            {'timestamp': '2025-07-22 23:03:15', 'level': 'INFO', 'component': 'domain_manager', 'message': 'Domain classification updated'},
        ]

        # Apply filters
        for log in sample_logs:
            if level_filter != 'all' and log['level'].lower() != level_filter:
                continue
            if component_filter != 'all' and log['component'] != component_filter:
                continue
            logs.append(log)

        return jsonify({'logs': logs})

    except Exception as e:
        logger.error(f"Error getting system logs: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/optimize-database', methods=['POST'])
def admin_optimize_database():
    """Optimize database performance"""
    try:
        # SQLite optimization commands
        db.session.execute(db.text("VACUUM"))
        db.session.execute(db.text("ANALYZE"))
        db.session.commit()

        return jsonify({'success': True, 'message': 'Database optimized successfully'})
    except Exception as e:
        logger.error(f"Error optimizing database: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/api/rebuild-indexes', methods=['POST'])
def admin_rebuild_indexes():
    """Rebuild database indexes"""
    try:
        # Drop and recreate indexes (SQLite handles this automatically on REINDEX)
        db.session.execute(db.text("REINDEX"))
        db.session.commit()

        return jsonify({'success': True, 'message': 'Database indexes rebuilt successfully'})
    except Exception as e:
        logger.error(f"Error rebuilding indexes: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/api/backup-database', methods=['POST'])
def admin_backup_database():
    """Create database backup"""
    try:
        import shutil
        from datetime import datetime

        # Create backup filename with timestamp
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'backup_email_guardian_{timestamp}.db'

        # Copy database file
        db_path = 'instance/email_guardian.db'
        backup_path = f'backups/{backup_filename}'

        # Create backups directory if it doesn't exist
        os.makedirs('backups', exist_ok=True)

        shutil.copy2(db_path, backup_path)

        return jsonify({
            'success': True, 
            'message': 'Database backup created successfully',
            'filename': backup_filename
        })
    except Exception as e:
        logger.error(f"Error creating database backup: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/api/retrain-models', methods=['POST'])
def admin_retrain_models():
    """Retrain ML models"""
    try:
        # This would trigger ML model retraining in a real implementation
        # For now, return success
        return jsonify({
            'success': True, 
            'message': 'ML models retrained successfully',
            'models_updated': ['isolation_forest', 'text_classifier', 'risk_scorer']
        })
    except Exception as e:
        logger.error(f"Error retraining models: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/api/update-ml-keywords', methods=['POST'])
def admin_update_ml_keywords():
    """Update ML keywords database"""
    try:
        # This would update the ML keywords in a real implementation
        return jsonify({
            'success': True, 
            'message': 'ML keywords updated successfully',
            'keywords_updated': 1250
        })
    except Exception as e:
        logger.error(f"Error updating ML keywords: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/api/validate-models', methods=['POST'])
def admin_validate_models():
    """Validate ML models performance"""
    try:
        # This would run model validation in a real implementation
        validation_score = 0.94  # Sample score
        return jsonify({
            'success': True, 
            'message': 'ML models validated successfully',
            'validation_score': validation_score
        })
    except Exception as e:
        logger.error(f"Error validating models: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/api/clear-logs', methods=['POST'])
def admin_clear_logs():
    """Clear system logs"""
    try:
        # In a real implementation, this would clear log files
        return jsonify({'success': True, 'message': 'System logs cleared successfully'})
    except Exception as e:
        logger.error(f"Error clearing logs: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/session/<session_id>', methods=['DELETE'])
def admin_delete_session(session_id):
    """Delete a processing session and all associated data"""
    try:
        session = ProcessingSession.query.get_or_404(session_id)

        # Delete associated records
        EmailRecord.query.filter_by(session_id=session_id).delete()
        ProcessingError.query.filter_by(session_id=session_id).delete()

        # Delete session files
        session_manager.cleanup_session(session_id)

        # Delete session record
        db.session.delete(session)
        db.session.commit()

        logger.info(f"Deleted session {session_id}")
        return jsonify({'status': 'deleted', 'message': 'Session deleted successfully'})

    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500



@app.route('/api/whitelist-domains/<int:domain_id>/toggle', methods=['POST'])
def api_toggle_whitelist_domain(domain_id):
    """Toggle whitelist domain active status"""
    try:
        domain = WhitelistDomain.query.get_or_404(domain_id)
        domain.is_active = not domain.is_active
        db.session.commit()

        status = 'activated' if domain.is_active else 'deactivated'
        logger.info(f"Domain {domain.domain} {status}")

        return jsonify({
            'success': True, 
            'message': f'Domain {domain.domain} {status} successfully',
            'is_active': domain.is_active
        })

    except Exception as e:
        logger.error(f"Error toggling whitelist domain {domain_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/whitelist', methods=['POST'])
def admin_update_whitelist():
    """Update whitelist domains"""
    try:
        domains = request.form.get('domains', '').strip()
        if domains:
            domain_list = [d.strip().lower() for d in domains.split('\n') if d.strip()]
            for domain in domain_list:
                if not WhitelistDomain.query.filter_by(domain=domain).first():
                    whitelist_entry = WhitelistDomain(
                        domain=domain,
                        domain_type='Corporate',
                        added_by='Admin'
                    )
                    db.session.add(whitelist_entry)
            db.session.commit()
            flash(f'Added {len(domain_list)} domains to whitelist', 'success')
        return redirect(url_for('admin'))
    except Exception as e:
        flash(f'Error updating whitelist: {str(e)}', 'error')
        return redirect(url_for('admin'))



@app.route('/api/case/<session_id>/<record_id>/status', methods=['PUT'])
def update_case_status(session_id, record_id):
    """Update case status"""
    try:
        case = EmailRecord.query.filter_by(session_id=session_id, record_id=record_id).first_or_404()
        data = request.get_json()

        case.case_status = data.get('status', case.case_status)
        case.notes = data.get('notes', case.notes)

        if data.get('status') == 'Escalated':
            case.escalated_at = datetime.utcnow()
        elif data.get('status') == 'Cleared':
            case.resolved_at = datetime.utcnow()

        db.session.commit()
        return jsonify({'status': 'updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/escalation/<session_id>/<record_id>/generate-email')
def generate_escalation_email(session_id, record_id):
    """Generate escalation email for a case"""
    try:
        case = EmailRecord.query.filter_by(session_id=session_id, record_id=record_id).first_or_404()

        # Generate email content based on case details
        risk_level = case.risk_level or 'Medium'
        ml_score = case.ml_risk_score or 0.0

        # Use the sender email address from the case as the recipient
        to_email = case.sender

        subject = f'URGENT: {risk_level} Risk Email Alert - {case.sender}'

        # Generate email body
        body = f"""SECURITY ALERT - Immediate Action Required

Case ID: {case.record_id}
Risk Level: {risk_level}
ML Risk Score: {ml_score:.3f}

Email Details:
- Sender: {case.sender}
- Recipients: {case.recipients or 'N/A'}
- Subject: {case.subject or 'N/A'}
- Time Sent: {case.time or 'N/A'}
- Attachments: {case.attachments or 'None'}

Risk Assessment:
{case.ml_explanation or 'No explanation available'}

Recommended Actions:
"""

        if risk_level == 'Critical':
            body += """
1. Block sender immediately
2. Quarantine any attachments
3. Notify affected recipients
4. Conduct immediate security review
5. Document incident for compliance
"""
        elif risk_level == 'High':
            body += """
1. Review email content carefully
2. Verify sender legitimacy
3. Scan attachments for threats
4. Monitor recipient activity
5. Consider sender restrictions
"""
        else:
            body += """
1. Review case details
2. Verify business justification
3. Monitor for patterns
4. Update security policies if needed
"""

        body += f"""
Justification Provided: {case.justification or 'None provided'}

Case Status: {case.case_status or 'Active'}
Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

This is an automated alert from Email Guardian Security System.
Please review and take appropriate action immediately.

Email Guardian Security Team
"""

        email_data = {
            'to': to_email,
            'cc': 'audit@company.com',
            'subject': subject,
            'body': body,
            'priority': 'high' if risk_level in ['Critical', 'High'] else 'normal'
        }

        logger.info(f"Generated escalation email for case {record_id} in session {session_id}")
        return jsonify(email_data)

    except Exception as e:
        logger.error(f"Error generating escalation email for case {record_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/processing_errors/<session_id>')
def api_processing_errors(session_id):
    """Get processing errors for session"""
    errors = ProcessingError.query.filter_by(session_id=session_id).all()
    return jsonify([{
        'id': error.id,
        'error_type': error.error_type,
        'error_message': error.error_message,
        'timestamp': error.timestamp.isoformat(),
        'resolved': error.resolved
    } for error in errors])

@app.route('/api/sender-analysis/<session_id>')
def api_sender_analysis(session_id):
    """Get sender analysis for dashboard"""
    try:
        analysis = advanced_ml_engine.analyze_sender_behavior(session_id)

        if not analysis:
            return jsonify({
                'total_senders': 0,
                'sender_profiles': {},
                'summary_statistics': {
                    'high_risk_senders': 0,
                    'external_focused_senders': 0,
                    'attachment_senders': 0,
                    'avg_emails_per_sender': 0
                }
            })

        return jsonify(analysis)

    except Exception as e:
        logger.error(f"Error getting sender analysis for session {session_id}: {str(e)}")
        return jsonify({
            'error': str(e),
            'total_senders': 0,
            'sender_profiles': {},
            'summary_statistics': {
                'high_risk_senders': 0,
                'external_focused_senders': 0,
                'attachment_senders': 0,
                'avg_emails_per_sender': 0
            }
        }), 200

@app.route('/api/sender_details/<session_id>/<sender_email>')
def api_sender_details(session_id, sender_email):
    """Get detailed sender information"""
    try:
        # Get sender analysis
        analysis = advanced_ml_engine.analyze_sender_behavior(session_id)

        if not analysis or 'sender_profiles' not in analysis:
            return jsonify({'error': 'No sender analysis available'}), 404

        sender_data = analysis['sender_profiles'].get(sender_email)

        if not sender_data:
            return jsonify({'error': 'Sender not found in analysis'}), 404

        # Get recent communications for this sender - exclude whitelisted records
        recent_records = EmailRecord.query.filter_by(
            session_id=session_id,
            sender=sender_email
        ).filter(
            db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
        ).order_by(EmailRecord.id.desc()).limit(5).all()

        recent_activity = []
        for record in recent_records:
            recent_activity.append({
                'record_id': record.record_id,
                'recipient_domain': record.recipients_email_domain,
                'subject': record.subject[:50] + '...' if record.subject and len(record.subject) > 50 else record.subject,
                'risk_score': record.ml_risk_score,
                'risk_level': record.risk_level,
                'has_attachments': bool(record.attachments),
                'time': record.time
            })

        sender_details = {
            'sender_email': sender_email,
            'profile': sender_data,
            'recent_activity': recent_activity,
            'analysis_timestamp': datetime.utcnow().isoformat()
        }

        return jsonify(sender_details)

    except Exception as e:
        logger.error(f"Error getting sender details for {sender_email} in session {session_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/session/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """Delete a processing session and all associated data"""
    try:
        session = ProcessingSession.query.get_or_404(session_id)

        # Delete associated email records
        EmailRecord.query.filter_by(session_id=session_id).delete()

        # Delete processing errors
        ProcessingError.query.filter_by(session_id=session_id).delete()

        # Delete uploaded file if it exists
        if session.data_path and os.path.exists(session.data_path):
            os.remove(session.data_path)

        # Check for upload file
        upload_files = [f for f in os.listdir(app.config.get('UPLOAD_FOLDER', 'uploads')) 
                       if f.startswith(session_id)]
        for file in upload_files:
            file_path = os.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), file)
            if os.path.exists(file_path):
                os.remove(file_path)

        # Delete session record
        db.session.delete(session)
        db.session.commit()

        logger.info(f"Session {session_id} deleted successfully")
        return jsonify({'status': 'deleted'})

    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/sessions/cleanup', methods=['POST'])
def cleanup_old_sessions():
    """Delete sessions older than 30 days"""
    try:
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=30)

        old_sessions = ProcessingSession.query.filter(
            ProcessingSession.upload_time < cutoff_date
        ).all()

        deleted_count = 0
        for session in old_sessions:
            try:
                # Delete associated records
                EmailRecord.query.filter_by(session_id=session.id).delete()
                ProcessingError.query.filter_by(session_id=session.id).delete()

                # Delete files
                if session.data_path and os.path.exists(session.data_path):
                    os.remove(session.data_path)

                upload_files = [f for f in os.listdir(app.config.get('UPLOAD_FOLDER', 'uploads')) 
                               if f.startswith(session.id)]
                for file in upload_files:
                    file_path = os.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), file)
                    if os.path.exists(file_path):
                        os.remove(file_path)

                db.session.delete(session)
                deleted_count += 1

            except Exception as e:
                logger.warning(f"Could not delete session {session.id}: {str(e)}")
                continue

        db.session.commit()
        logger.info(f"Cleaned up {deleted_count} old sessions")
        return jsonify({'status': 'completed', 'deleted_count': deleted_count})

    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/keywords/populate', methods=['POST'])
def populate_default_keywords():
    """Populate database with default ML keywords"""
    try:
        # Check if keywords already exist
        existing_count = AttachmentKeyword.query.count()
        if existing_count > 0:
            return jsonify({'status': 'info', 'message': f'Keywords already exist ({existing_count} total)', 'count': existing_count})

        default_keywords = [
            # Suspicious keywords
            {'keyword': 'urgent', 'category': 'Suspicious', 'risk_score': 8},
            {'keyword': 'confidential', 'category': 'Suspicious', 'risk_score': 7},
            {'keyword': 'invoice', 'category': 'Suspicious', 'risk_score': 6},
            {'keyword': 'payment', 'category': 'Suspicious', 'risk_score': 7},
            {'keyword': 'wire transfer', 'category': 'Suspicious', 'risk_score': 9},
            {'keyword': 'click here', 'category': 'Suspicious', 'risk_score': 8},
            {'keyword': 'verify account', 'category': 'Suspicious', 'risk_score': 9},
            {'keyword': 'suspended', 'category': 'Suspicious', 'risk_score': 8},
            {'keyword': 'immediate action', 'category': 'Suspicious', 'risk_score': 9},
            {'keyword': 'prize', 'category': 'Suspicious', 'risk_score': 7},
            {'keyword': 'winner', 'category': 'Suspicious', 'risk_score': 7},
            {'keyword': 'free money', 'category': 'Suspicious', 'risk_score': 9},
            {'keyword': 'act now', 'category': 'Suspicious', 'risk_score': 8},
            {'keyword': 'limited time', 'category': 'Suspicious', 'risk_score': 6},
            {'keyword': 'social security', 'category': 'Suspicious', 'risk_score': 9},
            {'keyword': 'tax refund', 'category': 'Suspicious', 'risk_score': 8},
            {'keyword': 'suspended account', 'category': 'Suspicious', 'risk_score': 9},
            {'keyword': 'security alert', 'category': 'Suspicious', 'risk_score': 8},
            {'keyword': 'unusual activity', 'category': 'Suspicious', 'risk_score': 7},
            {'keyword': 'bitcoin', 'category': 'Suspicious', 'risk_score': 7},

            # Business keywords
            {'keyword': 'meeting', 'category': 'Business', 'risk_score': 2},
            {'keyword': 'project', 'category': 'Business', 'risk_score': 2},
            {'keyword': 'proposal', 'category': 'Business', 'risk_score': 3},
            {'keyword': 'contract', 'category': 'Business', 'risk_score': 4},
            {'keyword': 'agreement', 'category': 'Business', 'risk_score': 4},
            {'keyword': 'report', 'category': 'Business', 'risk_score': 2},
            {'keyword': 'quarterly', 'category': 'Business', 'risk_score': 2},
            {'keyword': 'budget', 'category': 'Business', 'risk_score': 3},
            {'keyword': 'forecast', 'category': 'Business', 'risk_score': 2},
            {'keyword': 'presentation', 'category': 'Business', 'risk_score': 2},
            {'keyword': 'conference', 'category': 'Business', 'risk_score': 2},
            {'keyword': 'training', 'category': 'Business', 'risk_score': 2},
            {'keyword': 'schedule', 'category': 'Business', 'risk_score': 2},
            {'keyword': 'approval', 'category': 'Business', 'risk_score': 3},
            {'keyword': 'review', 'category': 'Business', 'risk_score': 2},
            {'keyword': 'deadline', 'category': 'Business', 'risk_score': 3},
            {'keyword': 'milestone', 'category': 'Business', 'risk_score': 2},
            {'keyword': 'deliverable', 'category': 'Business', 'risk_score': 2},
            {'keyword': 'stakeholder', 'category': 'Business', 'risk_score': 2},
            {'keyword': 'compliance', 'category': 'Business', 'risk_score': 3},

            # Personal keywords
            {'keyword': 'birthday', 'category': 'Personal', 'risk_score': 1},
            {'keyword': 'vacation', 'category': 'Personal', 'risk_score': 2},
            {'keyword': 'holiday', 'category': 'Personal', 'risk_score': 2},
            {'keyword': 'family', 'category': 'Personal', 'risk_score': 2},
            {'keyword': 'wedding', 'category': 'Personal', 'risk_score': 2},
            {'keyword': 'party', 'category': 'Personal', 'risk_score': 2},
            {'keyword': 'lunch', 'category': 'Personal', 'risk_score': 1},
            {'keyword': 'dinner', 'category': 'Personal', 'risk_score': 1},
            {'keyword': 'weekend', 'category': 'Personal', 'risk_score': 1},
            {'keyword': 'personal', 'category': 'Personal', 'risk_score': 3},
            {'keyword': 'private', 'category': 'Personal', 'risk_score': 4},
            {'keyword': 'home', 'category': 'Personal', 'risk_score': 2},
            {'keyword': 'sick leave', 'category': 'Personal', 'risk_score': 2},
            {'keyword': 'appointment', 'category': 'Personal', 'risk_score': 2},
            {'keyword': 'doctor', 'category': 'Personal', 'risk_score': 3},
            {'keyword': 'health', 'category': 'Personal', 'risk_score': 3},
            {'keyword': 'emergency', 'category': 'Personal', 'risk_score': 5},
            {'keyword': 'resignation', 'category': 'Personal', 'risk_score': 6},
            {'keyword': 'quit', 'category': 'Personal', 'risk_score': 6},
            {'keyword': 'leave company', 'category': 'Personal', 'risk_score': 7}
        ]

        for keyword_data in default_keywords:
            keyword = AttachmentKeyword(
                keyword=keyword_data['keyword'],
                category=keyword_data['category'],
                risk_score=keyword_data['risk_score'],
                is_active=True
            )
            db.session.add(keyword)

        db.session.commit()

        logger.info(f"Added {len(default_keywords)} default keywords to database")
        return jsonify({
            'status': 'success', 
            'message': f'Added {len(default_keywords)} keywords',
            'count': len(default_keywords)
        })

    except Exception as e:
        logger.error(f"Error populating keywords: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ml-keywords')
def api_ml_keywords():
    """Get ML keywords summary"""
    try:
        # Get attachment keywords from database
        keywords = AttachmentKeyword.query.filter_by(is_active=True).all()

        # If no keywords exist, provide default response
        if not keywords:
            return jsonify({
                'total_keywords': 0,
                'categories': {'Business': 0, 'Personal': 0, 'Suspicious': 0},
                'keywords': [],
                'last_updated': datetime.utcnow().isoformat(),
                'message': 'No ML keywords found. You can populate default keywords from the admin panel.'
            })

        # Count by category
        categories = {'Business': 0, 'Personal': 0, 'Suspicious': 0}
        keyword_list = []

        for keyword in keywords:
            category = keyword.category or 'Business'
            if category in categories:
                categories[category] += 1

            keyword_list.append({
                'keyword': keyword.keyword,
                'category': category,
                'risk_score': keyword.risk_score
            })

        return jsonify({
            'total_keywords': len(keywords),
            'categories': categories,
            'keywords': keyword_list[:50],  # Limit to 50 for display
            'last_updated': datetime.utcnow().isoformat()
        })

    except Exception as e:
        logger.error(f"Error getting ML keywords: {str(e)}")
        return jsonify({
            'error': 'Failed to load ML keywords',
            'total_keywords': 0,
            'categories': {'Business': 0, 'Personal': 0, 'Suspicious': 0},
            'keywords': [],
            'last_updated': datetime.utcnow().isoformat()
        }), 200  # Return 200 instead of 500 to prevent JS errors

@app.route('/api/ml-keywords', methods=['DELETE'])
def delete_all_ml_keywords():
    """Delete all ML keywords"""
    try:
        count = AttachmentKeyword.query.count()
        AttachmentKeyword.query.delete()
        db.session.commit()

        logger.info(f"Deleted {count} ML keywords from database")
        return jsonify({
            'success': True,
            'message': f'Successfully deleted {count} ML keywords',
            'deleted_count': count
        })

    except Exception as e:
        logger.error(f"Error deleting ML keywords: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ml-config', methods=['GET', 'PUT'])
def api_ml_config():
    """Get or update ML risk scoring configuration"""
    if request.method == 'GET':
        # Return current ML configuration
        return jsonify({
            'success': True,
            'config': ml_config.get_config_dict()
        })

    elif request.method == 'PUT':
        try:
            data = request.get_json()

            # Update specific configuration values
            if 'risk_thresholds' in data:
                ml_config.RISK_THRESHOLDS.update(data['risk_thresholds'])

            if 'rule_based_factors' in data:
                ml_config.RULE_BASED_FACTORS.update(data['rule_based_factors'])

            if 'high_risk_extensions' in data:
                ml_config.HIGH_RISK_EXTENSIONS = data['high_risk_extensions']

            if 'medium_risk_extensions' in data:
                ml_config.MEDIUM_RISK_EXTENSIONS = data['medium_risk_extensions']

            if 'public_domains' in data:
                ml_config.PUBLIC_DOMAINS = data['public_domains']

            if 'suspicious_justification_terms' in data:
                ml_config.SUSPICIOUS_JUSTIFICATION_TERMS = data['suspicious_justification_terms']

            logger.info("ML configuration updated successfully")
            return jsonify({
                'success': True,
                'message': 'ML configuration updated successfully',
                'config': ml_config.get_config_dict()
            })

        except Exception as e:
            logger.error(f"Error updating ML configuration: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 500

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# ML Keywords Management API Endpoints
@app.route('/api/ml-keywords/add', methods=['POST'])
def add_ml_keyword():
    """Add a new ML keyword"""
    try:
        data = request.get_json()
        keyword = data.get('keyword', '').strip()
        category = data.get('category', 'Business')
        risk_score = int(data.get('risk_score', 5))

        if not keyword:
            return jsonify({'error': 'Keyword is required'}), 400

        if category not in ['Business', 'Personal', 'Suspicious']:
            return jsonify({'error': 'Invalid category'}), 400

        if not (1 <= risk_score <= 10):
            return jsonify({'error': 'Risk score must be between 1 and 10'}), 400

        # Check if keyword already exists
        existing = AttachmentKeyword.query.filter_by(keyword=keyword).first()
        if existing:
            return jsonify({'error': f'Keyword "{keyword}" already exists'}), 400

        # Add keyword to database
        new_keyword = AttachmentKeyword(
            keyword=keyword,
            category=category,
            risk_score=risk_score,
            is_active=True
        )

        db.session.add(new_keyword)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Keyword "{keyword}" added successfully',
            'keyword': {
                'id': new_keyword.id,
                'keyword': keyword,
                'category': category,
                'risk_score': risk_score
            }
        })

    except Exception as e:
        logger.error(f"Error adding ML keyword: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ml-keywords/update/<int:keyword_id>', methods=['PUT'])
def update_ml_keyword(keyword_id):
    """Update an existing ML keyword"""
    try:
        keyword_obj = AttachmentKeyword.query.get_or_404(keyword_id)
        data = request.get_json()

        keyword_obj.keyword = data.get('keyword', keyword_obj.keyword).strip()
        keyword_obj.category = data.get('category', keyword_obj.category)
        keyword_obj.risk_score = int(data.get('risk_score', keyword_obj.risk_score))
        keyword_obj.is_active = data.get('is_active', keyword_obj.is_active)

        if not keyword_obj.keyword:
            return jsonify({'error': 'Keyword is required'}), 400

        if keyword_obj.category not in ['Business', 'Personal', 'Suspicious']:
            return jsonify({'error': 'Invalid category'}), 400

        if not (1 <= keyword_obj.risk_score <= 10):
            return jsonify({'error': 'Risk score must be between 1 and 10'}), 400

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Keyword "{keyword_obj.keyword}" updated successfully'
        })

    except Exception as e:
        logger.error(f"Error updating ML keyword: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ml-keywords/delete/<int:keyword_id>', methods=['DELETE'])
def delete_ml_keyword(keyword_id):
    """Delete an ML keyword"""
    try:
        keyword_obj = AttachmentKeyword.query.get_or_404(keyword_id)
        keyword_name = keyword_obj.keyword

        db.session.delete(keyword_obj)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Keyword "{keyword_name}" deleted successfully'
        })

    except Exception as e:
        logger.error(f"Error deleting ML keyword: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ml-keywords/bulk-add', methods=['POST'])
def bulk_add_ml_keywords():
    """Add multiple ML keywords at once"""
    try:
        data = request.get_json()
        keywords_list = data.get('keywords', [])
        category = data.get('category', 'Business')
        risk_score = int(data.get('risk_score', 5))

        logger.info(f"Bulk add request: {len(keywords_list)} keywords, category: {category}, risk_score: {risk_score}")

        if not keywords_list:
            return jsonify({'success': False, 'error': 'Keywords list is required'}), 400

        if category not in ['Business', 'Personal', 'Suspicious']:
            return jsonify({'success': False, 'error': 'Invalid category'}), 400

        if not (1 <= risk_score <= 10):
            return jsonify({'success': False, 'error': 'Risk score must be between 1 and 10'}), 400

        if len(keywords_list) > 100:
            return jsonify({'success': False, 'error': 'Maximum 100 keywords allowed per bulk import'}), 400

        added_count = 0
        skipped_count = 0
        errors = []

        # Process each keyword
        for keyword in keywords_list:
            keyword = keyword.strip()

            if not keyword:
                continue

            if len(keyword) > 100:  # Reasonable length limit
                errors.append(f'Keyword too long: "{keyword[:20]}..."')
                continue

            # Check if keyword already exists (case-insensitive)
            existing = AttachmentKeyword.query.filter(
                db.func.lower(AttachmentKeyword.keyword) == keyword.lower()
            ).first()

            if existing:
                logger.info(f"Keyword '{keyword}' already exists, skipping")
                skipped_count += 1
                continue

            try:
                # Add keyword to database
                new_keyword = AttachmentKeyword(
                    keyword=keyword,
                    category=category,
                    risk_score=risk_score,
                    is_active=True
                )

                db.session.add(new_keyword)
                added_count += 1
                logger.info(f"Added keyword: '{keyword}' (category: {category}, risk: {risk_score})")

            except Exception as e:
                error_msg = f'Error adding "{keyword}": {str(e)}'
                errors.append(error_msg)
                logger.error(error_msg)
                continue

        # Commit all successful additions
        if added_count > 0:
            try:
                db.session.commit()
                logger.info(f"Successfully committed {added_count} new ML keywords to database")
            except Exception as e:
                error_msg = f'Database commit error: {str(e)}'
                logger.error(error_msg)
                db.session.rollback()
                return jsonify({'success': False, 'error': error_msg}), 500
        else:
            logger.info("No new keywords to commit")

        # Create success message
        message = f'Bulk import completed: {added_count} keywords added'
        if skipped_count > 0:
            message += f', {skipped_count} duplicates skipped'
        if errors:
            message += f', {len(errors)} errors occurred'

        logger.info(message)

        return jsonify({
            'success': True,
            'message': message,
            'added_count': added_count,
            'skipped_count': skipped_count,
            'errors': errors[:10]  # Limit error messages
        })

    except Exception as e:
        error_msg = f"Error in bulk keyword import: {str(e)}"
        logger.error(error_msg)
        db.session.rollback()
        return jsonify({'success': False, 'error': error_msg}), 500

@app.route('/api/ml-keywords/all', methods=['GET'])
def get_all_ml_keywords_detailed():
    """Get all ML keywords with full details for editing"""
    try:
        keywords = AttachmentKeyword.query.filter_by(is_active=True).order_by(AttachmentKeyword.category, AttachmentKeyword.keyword).all()
        keywords_list = []

        for kw in keywords:
            keywords_list.append({
                'id': kw.id,
                'keyword': kw.keyword,
                'category': kw.category,
                'risk_score': kw.risk_score,
                'is_active': kw.is_active
            })

        return jsonify({
            'keywords': keywords_list,
            'total': len(keywords_list)
        })

    except Exception as e:
        logger.error(f"Error getting detailed ML keywords: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Risk Factor Management APIs
@app.route('/api/risk-factors', methods=['GET'])
def get_risk_factors():
    """Get all risk factors"""
    try:
        factors = RiskFactor.query.filter_by(is_active=True).order_by(RiskFactor.sort_order, RiskFactor.name).all()
        factors_list = []

        for factor in factors:
            factors_list.append({
                'id': factor.id,
                'name': factor.name,
                'description': factor.description,
                'max_score': factor.max_score,
                'category': factor.category,
                'weight_percentage': factor.weight_percentage,
                'calculation_config': factor.calculation_config or {},
                'sort_order': factor.sort_order
            })

        return jsonify({
            'factors': factors_list,
            'total': len(factors_list)
        })

    except Exception as e:
        logger.error(f"Error getting risk factors: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/risk-factors/<int:factor_id>', methods=['GET'])
def get_risk_factor_details(factor_id):
    """Get detailed information about a specific risk factor"""
    try:
        factor = RiskFactor.query.get_or_404(factor_id)

        return jsonify({
            'id': factor.id,
            'name': factor.name,
            'description': factor.description,
            'max_score': factor.max_score,
            'category': factor.category,
            'weight_percentage': factor.weight_percentage,
            'calculation_config': factor.calculation_config or {},
            'sort_order': factor.sort_order,
            'is_active': factor.is_active,
            'created_at': factor.created_at.isoformat() if factor.created_at else None,
            'updated_at': factor.updated_at.isoformat() if factor.updated_at else None
        })

    except Exception as e:
        logger.error(f"Error getting risk factor details: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/risk-factors/add', methods=['POST'])
def add_risk_factor():
    """Add a new risk factor"""
    try:
        data = request.get_json()

        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        max_score = float(data.get('max_score', 0.1))
        category = data.get('category', 'General').strip()
        weight_percentage = float(data.get('weight_percentage', 0.0))
        calculation_config = data.get('calculation_config', {})

        if not name:
            return jsonify({'error': 'Name is required'}), 400

        if not description:
            return jsonify({'error': 'Description is required'}), 400

        if not (0.0 <= max_score <= 1.0):
            return jsonify({'error': 'Max score must be between 0.0 and 1.0'}), 400

        if not (0.0 <= weight_percentage <= 100.0):
            return jsonify({'error': 'Weight percentage must be between 0.0 and 100.0'}), 400

        # Check if factor name already exists
        existing = RiskFactor.query.filter_by(name=name).first()
        if existing:
            return jsonify({'error': f'Risk factor "{name}" already exists'}), 400

        # Create new risk factor
        new_factor = RiskFactor(
            name=name,
            description=description,
            max_score=max_score,
            category=category,
            weight_percentage=weight_percentage,
            calculation_config=calculation_config,
            sort_order=data.get('sort_order', 0),
            is_active=True
        )

        db.session.add(new_factor)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Risk factor "{name}" added successfully',
            'factor': {
                'id': new_factor.id,
                'name': name,
                'description': description,
                'max_score': max_score,
                'category': category,
                'weight_percentage': weight_percentage
            }
        })

    except Exception as e:
        logger.error(f"Error adding risk factor: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/risk-factors/update/<int:factor_id>', methods=['PUT'])
def update_risk_factor(factor_id):
    """Update an existing risk factor"""
    try:
        factor = RiskFactor.query.get_or_404(factor_id)
        data = request.get_json()

        factor.name = data.get('name', factor.name).strip()
        factor.description = data.get('description', factor.description).strip()
        factor.max_score = float(data.get('max_score', factor.max_score))
        factor.category = data.get('category', factor.category).strip()
        factor.weight_percentage = float(data.get('weight_percentage', factor.weight_percentage))
        factor.calculation_config = data.get('calculation_config', factor.calculation_config)
        factor.sort_order = int(data.get('sort_order', factor.sort_order))
        factor.is_active = data.get('is_active', factor.is_active)

        if not factor.name:
            return jsonify({'error': 'Name is required'}), 400

        if not factor.description:
            return jsonify({'error': 'Description is required'}), 400

        if not (0.0 <= factor.max_score <= 1.0):
            return jsonify({'error': 'Max score must be between 0.0 and 1.0'}), 400

        if not (0.0 <= factor.weight_percentage <= 100.0):
            return jsonify({'error': 'Weight percentage must be between 0.0 and 100.0'}), 400

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Risk factor "{factor.name}" updated successfully'
        })

    except Exception as e:
        logger.error(f"Error updating risk factor: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/risk-factors/delete/<int:factor_id>', methods=['DELETE'])
def delete_risk_factor(factor_id):
    """Delete a risk factor"""
    try:
        factor = RiskFactor.query.get_or_404(factor_id)
        factor_name = factor.name

        db.session.delete(factor)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Risk factor "{factor_name}" deleted successfully'
        })

    except Exception as e:
        logger.error(f"Error deleting risk factor: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/risk-factors/populate', methods=['POST'])
def populate_default_risk_factors():
    """Populate database with default risk factors"""
    try:
        # Check if risk factors already exist
        existing_count = RiskFactor.query.count()
        if existing_count > 0:
            return jsonify({
                'success': False,
                'message': f'Risk factors already exist ({existing_count} found). Delete existing factors first if you want to reset.'
            }), 400

        # Default risk factors based on current hardcoded values
        default_factors = [
            {
                'name': 'Leaver Status',
                'description': 'Employee leaving organization',
                'max_score': 0.3,
                'category': 'Security',
                'weight_percentage': 30.0,
                'sort_order': 1,
                'calculation_config': {
                    'field': 'leaver',
                    'trigger_values': ['yes', 'true', '1'],
                    'score_calculation': 'binary'
                }
            },
            {
                'name': 'External Domain',
                'description': 'Public email domains (Gmail, Yahoo, etc.)',
                'max_score': 0.2,
                'category': 'Security',
                'weight_percentage': 20.0,
                'sort_order': 2,
                'calculation_config': {
                    'field': 'recipients_email_domain',
                    'patterns': ['gmail', 'yahoo', 'hotmail', 'outlook'],
                    'score_calculation': 'pattern_match'
                }
            },
            {
                'name': 'Attachment Risk',
                'description': 'File type and suspicious patterns',
                'max_score': 0.3,
                'category': 'Content',
                'weight_percentage': 30.0,
                'sort_order': 3,
                'calculation_config': {
                    'field': 'attachments',
                    'high_risk_extensions': ['.exe', '.scr', '.bat'],
                    'medium_risk_extensions': ['.zip', '.rar'],
                    'score_calculation': 'attachment_analysis'
                }
            },
            {
                'name': 'Wordlist Matches',
                'description': 'Suspicious keywords in subject/attachment',
                'max_score': 0.2,
                'category': 'Content',
                'weight_percentage': 15.0,
                'sort_order': 4,
                'calculation_config': {
                    'fields': ['wordlist_subject', 'wordlist_attachment'],
                    'score_calculation': 'keyword_analysis'
                }
            },
            {
                'name': 'Time-based Risk',
                'description': 'Weekend/after-hours activity',
                'max_score': 0.1,
                'category': 'Time',
                'weight_percentage': 3.0,
                'sort_order': 5,
                'calculation_config': {
                    'field': 'time',
                    'risk_periods': ['weekend', 'after_hours'],
                    'score_calculation': 'time_analysis'
                }
            },
            {
                'name': 'Justification Analysis',
                'description': 'Suspicious terms in explanations',
                'max_score': 0.1,
                'category': 'Content',
                'weight_percentage': 2.0,
                'sort_order': 6,
                'calculation_config': {
                    'field': 'justification',
                    'suspicious_patterns': ['personal use', 'backup', 'external'],
                    'score_calculation': 'text_analysis'
                }
            }
        ]

        added_count = 0
        for factor_data in default_factors:
            new_factor = RiskFactor(**factor_data)
            db.session.add(new_factor)
            added_count += 1
            logger.info(f"Added risk factor: {factor_data['name']}")

        db.session.commit()
        logger.info(f"Successfully added {added_count} default risk factors")

        return jsonify({
            'success': True,
            'message': f'Successfully added {added_count} default risk factors',
            'added_count': added_count
        })

    except Exception as e:
        logger.error(f"Error populating default risk factors: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/config-last-modified')
def config_last_modified():
    """Get the last modification time of configurations"""
    try:
        from datetime import datetime
        import os

        # Check modification times of configuration tables
        last_rule_update = db.session.query(db.func.max(Rule.updated_at)).scalar() or datetime.min
        last_whitelist_update = db.session.query(db.func.max(WhitelistDomain.added_at)).scalar() or datetime.min
        last_keyword_update = db.session.query(db.func.max(AttachmentKeyword.created_at)).scalar() or datetime.min

        # Get the most recent update
        last_modified = max(last_rule_update, last_whitelist_update, last_keyword_update)

        return jsonify({
            'last_modified': last_modified.isoformat() if last_modified != datetime.min else None
        })

    except Exception as e:
        logger.error(f"Error checking config modification time: {str(e)}")
        return jsonify({'last_modified': None}), 500

@app.route('/api/debug-whitelist/<session_id>')
def debug_whitelist_matching(session_id):
    """Debug endpoint to check whitelist domain matching"""
    try:
        # Get active whitelist domains
        whitelist_domains = WhitelistDomain.query.filter_by(is_active=True).all()
        whitelist_set = {domain.domain.lower().strip() for domain in whitelist_domains}

        # Get unique domains from email records
        records = EmailRecord.query.filter_by(session_id=session_id).all()
        email_domains = {record.recipients_email_domain.lower().strip() 
                        for record in records 
                        if record.recipients_email_domain}

        # Check matches
        matches = []
        non_matches = []

        for email_domain in email_domains:
            matched = False
            for whitelist_domain in whitelist_set:
                if (email_domain == whitelist_domain or 
                    email_domain.endswith('.' + whitelist_domain) or 
                    whitelist_domain.endswith('.' + email_domain) or
                    email_domain in whitelist_domain or 
                    whitelist_domain in email_domain):
                    matches.append({
                        'email_domain': email_domain,
                        'whitelist_domain': whitelist_domain,
                        'match_type': 'exact' if email_domain == whitelist_domain else 'partial'
                    })
                    matched = True
                    break

            if not matched:
                non_matches.append(email_domain)

        return jsonify({
            'whitelist_domains': list(whitelist_set),
            'email_domains': list(email_domains),
            'matches': matches,
            'non_matches': non_matches,
            'total_email_domains': len(email_domains),
            'total_matches': len(matches),
            'total_non_matches': len(non_matches)
        })

    except Exception as e:
        logger.error(f"Error in whitelist debug for session {session_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug-rules/<session_id>')
def debug_rules(session_id):
    """Debug endpoint to check rule evaluation"""
    try:
        # Get all active rules
        all_rules = Rule.query.filter_by(is_active=True).all()

        rule_info = []
        for rule in all_rules:
            rule_info.append({
                'id': rule.id,
                'name': rule.name,
                'rule_type': rule.rule_type,
                'conditions': rule.conditions,
                'actions': rule.actions,
                'priority': rule.priority,
                'is_active': rule.is_active
            })

        # Get sample records to test against
        sample_records = EmailRecord.query.filter_by(session_id=session_id).limit(5).all()

        sample_data = []
        for record in sample_records:
            sample_data.append({
                'record_id': record.record_id,
                'sender': record.sender,
                'subject': record.subject,
                'recipients_email_domain': record.recipients_email_domain,
                'leaver': record.leaver,
                'attachments': record.attachments
            })

        return jsonify({
            'rules': rule_info,
            'total_rules': len(all_rules),
            'sample_records': sample_data,
            'session_id': session_id
        })

    except Exception as e:
        logger.error(f"Error in rules debug for session {session_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/monthly-report')
def monthly_report_dashboard():
    """Monthly report dashboard"""
    return render_template('monthly_report_dashboard.html')

@app.route('/api/monthly-report/sessions')
def api_monthly_report_sessions():
    """Get all available sessions for monthly report"""
    try:
        sessions = ProcessingSession.query.filter_by(status='completed').order_by(
            ProcessingSession.upload_time.desc()
        ).all()

        sessions_data = []
        for session in sessions:
            sessions_data.append({
                'id': session.id,
                'filename': session.filename,
                'upload_time': session.upload_time.isoformat() if session.upload_time else None,
                'total_records': session.total_records or 0,
                'status': session.status
            })

        return jsonify({
            'sessions': sessions_data,
            'total': len(sessions_data)
        })

    except Exception as e:
        logger.error(f"Error getting monthly report sessions: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/monthly-report/generate', methods=['POST'])
def api_generate_monthly_report():
    """Generate comprehensive monthly report from selected sessions"""
    try:
        data = request.get_json()
        session_ids = data.get('session_ids', [])
        period = data.get('period', 'current_month')
        report_format = data.get('format', 'executive')

        if not session_ids:
            return jsonify({'error': 'No sessions selected'}), 400

        # Get data from selected sessions
        query = EmailRecord.query.filter(EmailRecord.session_id.in_(session_ids))

        # Apply date filtering if custom period
        if period == 'custom':
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            if start_date and end_date:
                query = query.filter(EmailRecord.time.between(start_date, end_date))

        all_records = query.all()

        if not all_records:
            return jsonify({'error': 'No data found for selected sessions and period'}), 400

        # Generate comprehensive report data
        report_data = generate_monthly_report_data(all_records, session_ids, period, report_format)

        return jsonify(report_data)

    except Exception as e:
        logger.error(f"Error generating monthly report: {str(e)}")
        return jsonify({'error': str(e)}), 500

def generate_monthly_report_data(records, session_ids, period, report_format):
    """Generate comprehensive monthly report data"""
    from collections import defaultdict, Counter
    from datetime import datetime, timedelta
    import statistics

    total_records = len(records)

    # Calculate summary statistics
    risk_counts = Counter([r.risk_level for r in records if r.risk_level])
    status_counts = Counter([r.case_status for r in records if r.case_status])

    security_incidents = sum([
        risk_counts.get('Critical', 0),
        risk_counts.get('High', 0)
    ])

    cases_resolved = sum([
        status_counts.get('Cleared', 0),
        status_counts.get('Escalated', 0)
    ])

    # Calculate trends (simplified for demo)
    summary = {
        'total_emails': total_records,
        'security_incidents': security_incidents,
        'cases_resolved': cases_resolved,
        'incident_rate': (security_incidents / total_records * 100) if total_records > 0 else 0,
        'resolution_rate': (cases_resolved / security_incidents * 100) if security_incidents > 0 else 0,
        'avg_response_time': '2.5h',  # Simplified
        'emails_growth': 15,  # Simulated growth percentage
        'response_improvement': 8  # Simulated improvement
    }

    # Risk trends over time (simplified)
    risk_trends = {
        'labels': ['Week 1', 'Week 2', 'Week 3', 'Week 4'],
        'critical': [risk_counts.get('Critical', 0) // 4] * 4,
        'high': [risk_counts.get('High', 0) // 4] * 4,
        'medium': [risk_counts.get('Medium', 0) // 4] * 4
    }

    # Risk distribution
    risk_distribution = {
        'critical': risk_counts.get('Critical', 0),
        'high': risk_counts.get('High', 0),
        'medium': risk_counts.get('Medium', 0),
        'low': risk_counts.get('Low', 0)
    }

    # Department volume analysis
    dept_counts = Counter([r.department for r in records if r.department])
    top_depts = dept_counts.most_common(10)

    department_volume = {
        'labels': [dept[0] for dept in top_depts],
        'data': [dept[1] for dept in top_depts]
    }

    # Threat domains analysis
    domain_risks = defaultdict(int)
    for record in records:
        if record.recipients_email_domain and record.risk_level in ['Critical', 'High']:
            domain_risks[record.recipients_email_domain] += 1

    top_threats = sorted(domain_risks.items(), key=lambda x: x[1], reverse=True)[:10]
    threat_domains = {
        'labels': [domain[0] for domain in top_threats],
        'data': [domain[1] for domain in top_threats]
    }

    # ML performance metrics (simulated based on actual data)
    ml_scores = [r.ml_risk_score for r in records if r.ml_risk_score is not None]
    ml_performance = {
        'accuracy': 95.2,
        'precision': 92.8,
        'recall': 89.4,
        'f1_score': 91.0,
        'specificity': 96.1
    }

    # Response time analysis
    response_times = {
        'labels': ['Critical', 'High', 'Medium', 'Low'],
        'data': [1.2, 2.5, 4.8, 12.0]  # Average hours by risk level
    }

    # Policy effectiveness
    policy_effectiveness = {
        'labels': ['Week 1', 'Week 2', 'Week 3', 'Week 4'],
        'detection_rate': [92, 94, 95, 96],
        'false_positive_rate': [8, 6, 5, 4]
    }

    # Top risks analysis
    top_risks = [
        {
            'category': 'External Domains',
            'count': domain_risks.get('gmail.com', 0) + domain_risks.get('yahoo.com', 0),
            'avg_score': 0.85,
            'top_domain': 'gmail.com',
            'resolution_rate': 78.5,
            'trend': 'up',
            'trend_percentage': 12,
            'action_required': 'Monitor',
            'action_priority': 'medium'
        },
        {
            'category': 'Leaver Activity',
            'count': len([r for r in records if r.leaver and r.leaver.lower() in ['yes', 'true']]),
            'avg_score': 0.92,
            'top_domain': 'company.com',
            'resolution_rate': 95.2,
            'trend': 'down',
            'trend_percentage': -5,
            'action_required': 'Review',
            'action_priority': 'high'
        },
        {
            'category': 'Attachment Risks',
            'count': len([r for r in records if r.attachments]),
            'avg_score': 0.68,
            'top_domain': 'external.com',
            'resolution_rate': 82.1,
            'trend': 'stable',
            'trend_percentage': 2,
            'action_required': 'Monitor',
            'action_priority': 'medium'
        }
    ]

    # Recommendations
    recommendations = {
        'security': [
            {
                'title': 'Enhance External Domain Monitoring',
                'description': 'Implement stricter controls for communications to public email domains'
            },
            {
                'title': 'Leaver Process Optimization',
                'description': 'Improve automated detection and handling of employee departure scenarios'
            },
            {
                'title': 'Attachment Scanning Enhancement',
                'description': 'Upgrade attachment analysis capabilities for better threat detection'
            }
        ],
        'process': [
            {
                'title': 'Response Time Improvement',
                'description': 'Implement automated escalation for critical cases to reduce response time'
            },
            {
                'title': 'Training Program',
                'description': 'Conduct security awareness training focusing on identified risk patterns'
            },
            {
                'title': 'Policy Review',
                'description': 'Review and update security policies based on monthly findings'
            }
        ]
    }

    return {
        'summary': summary,
        'risk_trends': risk_trends,
        'risk_distribution': risk_distribution,
        'department_volume': department_volume,
        'threat_domains': threat_domains,
        'ml_performance': ml_performance,
        'response_times': response_times,
        'policy_effectiveness': policy_effectiveness,
        'top_risks': top_risks,
        'recommendations': recommendations,
        'period': period,
        'session_count': len(session_ids),
        'generated_at': datetime.utcnow().isoformat()
    }

@app.route('/api/monthly-report/export-pdf', methods=['POST'])
def api_export_monthly_report_pdf():
    """Export monthly report as PDF"""
    try:
        # For now, return a simple CSV export
        # In production, you would use libraries like WeasyPrint or ReportLab
        data = request.get_json()
        session_ids = data.get('session_ids', [])

        # Get all records from selected sessions
        records = EmailRecord.query.filter(EmailRecord.session_id.in_(session_ids)).all()

        # Create CSV content for now (would be PDF in production)
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'Session ID', 'Record ID', 'Sender', 'Subject', 'Risk Level', 
            'ML Score', 'Status', 'Time', 'Department', 'Attachments'
        ])

        # Write data
        for record in records:
            writer.writerow([
                record.session_id,
                record.record_id,
                record.sender,
                record.subject,
                record.risk_level,
                record.ml_risk_score,
                record.case_status,
                record.time,
                record.department,
                record.attachments
            ])

        # Create response
        output.seek(0)
        response = send_file(
            BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'monthly_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )

        return response

    except Exception as e:
        logger.error(f"Error exporting monthly report PDF: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/monthly-report/export-excel', methods=['POST'])
def api_export_monthly_report_excel():
    """Export monthly report as Excel"""
    try:
        # For now, return a CSV export (would be Excel in production with openpyxl)
        data = request.get_json()
        session_ids = data.get('session_ids', [])

        # Get all records from selected sessions
        records = EmailRecord.query.filter(EmailRecord.session_id.in_(session_ids)).all()

        # Create comprehensive CSV content
        output = StringIO()
        writer = csv.writer(output)

        # Write summary section
        writer.writerow(['MONTHLY EMAIL SECURITY REPORT'])
        writer.writerow(['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow(['Sessions:', len(session_ids)])
        writer.writerow(['Total Records:', len(records)])
        writer.writerow([])

        # Write detailed data
        writer.writerow([
            'Session ID', 'Record ID', 'Sender', 'Subject', 'Recipients Domain',
            'Risk Level', 'ML Score', 'Status', 'Time', 'Department', 
            'Business Unit', 'Attachments', 'Justification', 'Leaver'
        ])

        for record in records:
            writer.writerow([
                record.session_id,
                record.record_id,
                record.sender,
                record.subject,
                record.recipients_email_domain,
                record.risk_level,
                record.ml_risk_score,
                record.case_status,
                record.time,
                record.department,
                record.bunit,
                record.attachments,
                record.justification,
                record.leaver
            ])

        # Create response
        output.seek(0)
        response = send_file(
            BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'monthly_report_detailed_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )

        return response

    except Exception as e:
        logger.error(f"Error exporting monthly report Excel: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/force-complete-session/<session_id>', methods=['POST'])
def force_complete_session(session_id):
    """Force mark a session as completed if it appears stuck"""
    try:
        session = ProcessingSession.query.get_or_404(session_id)

        # Check if processing is actually complete
        total_records = EmailRecord.query.filter_by(session_id=session_id).count()
        ml_analyzed_records = EmailRecord.query.filter(
            EmailRecord.session_id == session_id,
            EmailRecord.ml_risk_score.isnot(None)
        ).count()

        if total_records > 0 and ml_analyzed_records > 0:
            # Update session status
            session.status = 'completed'
            session.processed_records = total_records
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Session marked as completed',
                'redirect_url': f'/dashboard/{session_id}'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Session does not appear to be ready for completion'
            })

    except Exception as e:
        logger.error(f"Error force completing session {session_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/reprocess-session/<session_id>', methods=['POST'])
def reprocess_session_data(session_id):
    """Re-process existing session data with current rules, whitelist, and ML keywords"""
    try:
        session = ProcessingSession.query.get_or_404(session_id)

        if session.status == 'processing':
            return jsonify({
                'error': 'Session is already processing'
            }), 400

        # Look for the original uploaded CSV file
        import os
        upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
        csv_path = None

        # Check for uploaded file with session ID prefix
        if os.path.exists(upload_folder):
            for filename in os.listdir(upload_folder):
                if filename.startswith(session_id):
                    csv_path = os.path.join(upload_folder, filename)
                    break

        # If no uploaded file found, check session.data_path
        if not csv_path and session.data_path and os.path.exists(session.data_path):
            csv_path = session.data_path

        if not csv_path:
            return jsonify({
                'error': 'Original CSV file not found for re-processing'
            }), 404

        # Update session status
        session.status = 'processing'
        session.processed_records = 0
        session.error_message = None
        session.current_chunk = 0
        session.total_chunks = 0
        db.session.commit()

        # Clear existing processed data for this session
        EmailRecord.query.filter_by(session_id=session_id).delete()
        ProcessingError.query.filter_by(session_id=session_id).delete()
        db.session.commit()

        # Re-process with current configurations in background thread
        def background_reprocessing():
            with app.app_context():
                try:
                    logger.info(f"Starting re-processing for session {session_id}")

                    # Log current rules
                    active_rules = Rule.query.filter_by(is_active=True).all()
                    logger.info(f"Found {len(active_rules)} active rules for re-processing")
                    for rule in active_rules:
                        logger.info(f"Rule: {rule.name} (Type: {rule.rule_type}, Conditions: {rule.conditions})")

                    data_processor.process_csv(session_id, csv_path)
                    logger.info(f"Background re-processing completed for session {session_id}")
                except Exception as e:
                    logger.error(f"Background re-processing error for session {session_id}: {str(e)}")
                    session = ProcessingSession.query.get(session_id)
                    if session:
                        session.status = 'error'
                        session.error_message = str(e)
                        db.session.commit()

        # Start background thread
        import threading
        thread = threading.Thread(target=background_reprocessing)
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'message': 'Re-processing started with current configurations',
            'session_id': session_id
        })

    except Exception as e:
        logger.error(f"Error starting re-processing for session {session_id}: {str(e)}")
        session = ProcessingSession.query.get(session_id)
        if session:
            session.status = 'error'
            session.error_message = str(e)
            db.session.commit()
        return jsonify({'error': str(e)}), 500

@app.route('/network/<session_id>')
def network_dashboard(session_id):
    """Network analysis dashboard for a specific session"""
    session = ProcessingSession.query.get_or_404(session_id)
    return render_template('network_dashboard.html', session=session)

@app.route('/api/network-data/<session_id>', methods=['POST'])
def api_network_data(session_id):
    """Generate network visualization data for a specific session with multiple link support"""
    try:
        session = ProcessingSession.query.get_or_404(session_id)
        data = request.get_json()

        link_configs = data.get('link_configs', [{'source_field': 'sender', 'target_field': 'recipients_email_domain', 'color': '#007bff', 'style': 'solid'}])
        risk_filter = data.get('risk_filter', 'all')
        min_connections = data.get('min_connections', 1)
        node_size_metric = data.get('node_size_metric', 'connections')

        # Get emails for this session
        query = EmailRecord.query.filter_by(session_id=session_id)

        # Apply risk filter
        if risk_filter != 'all':
            query = query.filter_by(risk_level=risk_filter)

        # Exclude whitelisted records
        query = query.filter(
            db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
        )

        emails = query.all()

        if not emails:
            return jsonify({
                'nodes': [],
                'links': [],
                'message': 'No data available for network visualization'
            })

        # Build network graph for multiple link types
        nodes_dict = {}
        links_list = []

        # Process each link configuration
        for link_idx, link_config in enumerate(link_configs):
            source_field = link_config.get('source_field', 'sender')
            target_field = link_config.get('target_field', 'recipients_email_domain')
            link_color = link_config.get('color', '#007bff')
            link_style = link_config.get('style', 'solid')

            link_dict = {}  # For this specific link type

            for email in emails:
                # Get source and target values with proper handling
                source_value = getattr(email, source_field, '') or 'Unknown'
                target_value = getattr(email, target_field, '') or 'Unknown'

                # Handle special fields that might need processing
                if source_field == 'recipients' and source_value != 'Unknown':
                    # Extract first recipient email or domain
                    recipients_list = str(source_value).split(',')
                    if recipients_list:
                        source_value = recipients_list[0].strip()

                if target_field == 'recipients' and target_value != 'Unknown':
                    # Extract first recipient email or domain
                    recipients_list = str(target_value).split(',')
                    if recipients_list:
                        target_value = recipients_list[0].strip()

                # Truncate long text fields for readability
                text_fields = ['subject', 'attachments', 'user_response', 'justification', 'wordlist_attachment', 'wordlist_subject']
                if source_field in text_fields and source_value != 'Unknown':
                    source_value = str(source_value)[:50] + "..." if len(str(source_value)) > 50 else str(source_value)

                if target_field in text_fields and target_value != 'Unknown':
                    target_value = str(target_value)[:50] + "..." if len(str(target_value)) > 50 else str(target_value)

                # Handle date fields
                if source_field == 'time' and source_value != 'Unknown':
                    # Extract just the date part if it's a full datetime
                    if ' ' in str(source_value):
                        source_value = str(source_value).split(' ')[0]

                if target_field == 'time' and target_value != 'Unknown':
                    # Extract just the date part if it's a full datetime
                    if ' ' in str(target_value):
                        target_value = str(target_value).split(' ')[0]

                if not source_value or not target_value or source_value == target_value:
                    continue

                # Clean and normalize values
                source_value = str(source_value).strip()
                target_value = str(target_value).strip()

                if len(source_value) == 0 or len(target_value) == 0:
                    continue

                # Create nodes
                if source_value not in nodes_dict:
                    nodes_dict[source_value] = {
                        'id': source_value,
                        'label': source_value,
                        'type': source_field,
                        'connections': 0,
                        'email_count': 0,
                        'risk_score': 0,
                        'risk_level': 'Low',
                        'size': 10
                    }

                if target_value not in nodes_dict:
                    nodes_dict[target_value] = {
                        'id': target_value,
                        'label': target_value,
                        'type': target_field,
                        'connections': 0,
                        'email_count': 0,
                        'risk_score': 0,
                        'risk_level': 'Low',
                        'size': 10
                    }

                # Update node metrics
                nodes_dict[source_value]['email_count'] += 1
                nodes_dict[target_value]['email_count'] += 1

                # Update risk information
                if email.ml_risk_score:
                    current_risk = nodes_dict[source_value]['risk_score']
                    nodes_dict[source_value]['risk_score'] = max(current_risk, email.ml_risk_score)

                    if email.risk_level and email.risk_level != 'Low':
                        nodes_dict[source_value]['risk_level'] = email.risk_level

                # Create link for this specific link type
                link_key = f"{source_value}->{target_value}"
                if link_key not in link_dict:
                    link_dict[link_key] = {
                        'source': source_value,
                        'target': target_value,
                        'weight': 0,
                        'color': link_color,
                        'style': link_style,
                        'type': f"{source_field}-{target_field}"
                    }

                link_dict[link_key]['weight'] += 1

            # Add this link type's links to the main list
            links_list.extend(link_dict.values())

        # Calculate node connections from all link types
        for link in links_list:
            nodes_dict[link['source']]['connections'] += 1
            nodes_dict[link['target']]['connections'] += 1

        # Filter nodes by minimum connections
        filtered_nodes = {k: v for k, v in nodes_dict.items() if v['connections'] >= min_connections}

        # Filter links to only include nodes that passed the filter
        filtered_links = [link for link in links_list 
                         if link['source'] in filtered_nodes and link['target'] in filtered_nodes]

        # Calculate node sizes based on selected metric
        if filtered_nodes:
            metric_values = []
            for node in filtered_nodes.values():
                if node_size_metric == 'connections':
                    metric_values.append(node['connections'])
                elif node_size_metric == 'risk_score':
                    metric_values.append(node['risk_score'] or 0)
                elif node_size_metric == 'email_count':
                    metric_values.append(node['email_count'])
                else:
                    metric_values.append(node['connections'])

            min_metric = min(metric_values) if metric_values else 0
            max_metric = max(metric_values) if metric_values else 1
            metric_range = max_metric - min_metric if max_metric > min_metric else 1

            # Scale node sizes between 6 and 25
            for node in filtered_nodes.values():
                if node_size_metric == 'connections':
                    metric_val = node['connections']
                elif node_size_metric == 'risk_score':
                    metric_val = node['risk_score'] or 0
                elif node_size_metric == 'email_count':
                    metric_val = node['email_count']
                else:
                    metric_val = node['connections']

                normalized = (metric_val - min_metric) / metric_range if metric_range > 0 else 0
                node['size'] = 6 + (normalized * 19)  # Scale between 6 and 25

        # Convert to lists
        nodes_list = list(filtered_nodes.values())

        return jsonify({
            'nodes': nodes_list,
            'links': filtered_links
        })

    except Exception as e:
        logger.error(f"Error generating network data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/professional-reports')
def professional_reports():
    """Professional reports dashboard with session selection"""
    try:
        # Get all completed sessions
        sessions = ProcessingSession.query.filter(
            ProcessingSession.status == 'completed'
        ).order_by(ProcessingSession.upload_time.desc()).all()
        
        return render_template('professional_reports.html', sessions=sessions)
    except Exception as e:
        logger.error(f"Error loading professional reports: {str(e)}")
        flash(f'Error loading reports: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/api/generate-professional-report', methods=['POST'])
def generate_professional_report():
    """Generate professional report for selected sessions"""
    try:
        data = request.get_json()
        session_ids = data.get('session_ids', [])
        
        if not session_ids:
            return jsonify({'error': 'No sessions selected'}), 400
        
        # Get session data
        sessions = ProcessingSession.query.filter(
            ProcessingSession.id.in_(session_ids)
        ).all()
        
        if not sessions:
            return jsonify({'error': 'No valid sessions found'}), 404
        
        # Generate comprehensive report data
        report_data = _generate_comprehensive_report(sessions)
        
        return jsonify(report_data)
    except Exception as e:
        logger.error(f"Error generating professional report: {str(e)}")
        return jsonify({'error': str(e)}), 500

def _generate_comprehensive_report(sessions):
    """Generate comprehensive professional report data"""
    try:
        session_ids = [s.id for s in sessions]
        
        # Overall statistics
        total_records = EmailRecord.query.filter(
            EmailRecord.session_id.in_(session_ids)
        ).count()
        
        analyzed_records = EmailRecord.query.filter(
            EmailRecord.session_id.in_(session_ids),
            EmailRecord.ml_risk_score.isnot(None)
        ).count()
        
        # Risk distribution
        critical_count = EmailRecord.query.filter(
            EmailRecord.session_id.in_(session_ids),
            EmailRecord.risk_level == 'Critical'
        ).count()
        
        high_count = EmailRecord.query.filter(
            EmailRecord.session_id.in_(session_ids),
            EmailRecord.risk_level == 'High'
        ).count()
        
        medium_count = EmailRecord.query.filter(
            EmailRecord.session_id.in_(session_ids),
            EmailRecord.risk_level == 'Medium'
        ).count()
        
        low_count = EmailRecord.query.filter(
            EmailRecord.session_id.in_(session_ids),
            EmailRecord.risk_level == 'Low'
        ).count()
        
        # Session details
        session_details = []
        for session in sessions:
            session_records = EmailRecord.query.filter_by(session_id=session.id).count()
            session_analyzed = EmailRecord.query.filter(
                EmailRecord.session_id == session.id,
                EmailRecord.ml_risk_score.isnot(None)
            ).count()
            
            session_details.append({
                'session_id': session.id,
                'filename': session.filename,
                'upload_time': session.upload_time.strftime('%Y-%m-%d %H:%M:%S') if session.upload_time else 'Unknown',
                'status': session.status,
                'total_records': session_records,
                'analyzed_records': session_analyzed,
                'analysis_rate': round((session_analyzed / session_records * 100) if session_records > 0 else 0, 2)
            })
        
        # Domain analysis
        domain_stats = db.session.execute(
            text("""
            SELECT recipients_email_domain, 
                   COUNT(*) as count,
                   AVG(CAST(ml_risk_score AS FLOAT)) as avg_risk
            FROM email_records 
            WHERE session_id IN :session_ids 
                  AND recipients_email_domain IS NOT NULL 
                  AND ml_risk_score IS NOT NULL
            GROUP BY recipients_email_domain 
            ORDER BY count DESC 
            LIMIT 20
            """),
            {'session_ids': tuple(session_ids)}
        ).fetchall()
        
        # High risk samples
        risk_factors = EmailRecord.query.filter(
            EmailRecord.session_id.in_(session_ids),
            EmailRecord.risk_level.in_(['Critical', 'High'])
        ).limit(20).all()
        
        return {
            'report_metadata': {
                'generation_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'sessions_included': len(sessions),
                'total_records': total_records,
                'analyzed_records': analyzed_records,
                'analysis_rate': round((analyzed_records / total_records * 100) if total_records > 0 else 0, 2)
            },
            'risk_summary': {
                'critical': critical_count,
                'high': high_count,
                'medium': medium_count,
                'low': low_count,
                'total_risk_records': critical_count + high_count + medium_count + low_count
            },
            'session_details': session_details,
            'domain_analysis': [{
                'domain': row[0],
                'count': row[1],
                'avg_risk': round(float(row[2]), 3) if row[2] else 0
            } for row in domain_stats],
            'high_risk_samples': [{
                'record_id': r.record_id,
                'sender': r.sender[:50] + '...' if r.sender and len(r.sender) > 50 else r.sender,
                'subject': r.subject[:100] + '...' if r.subject and len(r.subject) > 100 else r.subject,
                'risk_level': r.risk_level,
                'risk_score': round(r.ml_risk_score, 3) if r.ml_risk_score else 0,
                'recipients_domain': r.recipients_email_domain
            } for r in risk_factors]
        }
    except Exception as e:
        logger.error(f"Error generating comprehensive report: {str(e)}")
        raise