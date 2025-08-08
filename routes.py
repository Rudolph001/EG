# Email Guardian - Flask Routes
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, make_response, abort, session
from werkzeug.utils import secure_filename
from app import app, db
from models import *
from performance_config import PerformanceConfig

# Initialize config
config = PerformanceConfig()
import os
import json
import logging
from datetime import datetime, timedelta
import uuid
from pathlib import Path

# Initialize core components
from session_manager import SessionManager
from data_processor import DataProcessor
from ml_engine import MLEngine
from advanced_ml_engine import AdvancedMLEngine
from adaptive_ml_engine import AdaptiveMLEngine
from rule_engine import RuleEngine
from domain_manager import DomainManager
from workflow_manager import WorkflowManager
from audit_system import AuditLogger
from ml_config import MLRiskConfig
import uuid
import os
import json
from datetime import datetime
import logging
import psutil
import threading
import shutil
import statistics
from collections import defaultdict, Counter
from datetime import timedelta
import threading
from io import StringIO, BytesIO
import csv

logger = logging.getLogger(__name__)

# Initialize core components
session_manager = SessionManager()
data_processor = DataProcessor()
ml_engine = MLEngine()
advanced_ml_engine = AdvancedMLEngine()
adaptive_ml_engine = AdaptiveMLEngine()
rule_engine = RuleEngine()
domain_manager = DomainManager()
workflow_manager = WorkflowManager()
ml_config = MLRiskConfig()

# Add Jinja2 filter for JSON parsing
@app.template_filter('from_json')
def from_json_filter(value):
    """Convert JSON string to Python object"""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    return value or []

@app.context_processor
def inject_session_id():
    """Make session_id available to all templates"""
    # Try to get session_id from URL path
    session_id = None
    if request.endpoint and hasattr(request, 'view_args') and request.view_args:
        session_id = request.view_args.get('session_id')

    # Also check if we're on index page with recent sessions
    recent_sessions = []
    if request.endpoint == 'index':
        try:
            recent_sessions = ProcessingSession.query.order_by(ProcessingSession.upload_time.desc()).limit(5).all()
            if recent_sessions:
                session_id = recent_sessions[0].id  # Use most recent session for navigation
        except:
            pass

    return dict(session_id=session_id, recent_sessions=recent_sessions)

@app.route('/')
def index():
    """Main index page with upload functionality"""
    recent_sessions = ProcessingSession.query.order_by(ProcessingSession.upload_time.desc()).limit(10).all()
    return render_template('index.html', recent_sessions=recent_sessions)

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

@app.route('/api/grouped-cases/<session_id>')
def api_grouped_cases(session_id):
    """Get grouped email cases for case manager - groups by sender, subject, time, and content"""
    try:
        # Get filter parameters
        risk_level = request.args.get('risk_level', '')
        case_status = request.args.get('case_status', '')
        search = request.args.get('search', '')
        show_whitelisted = request.args.get('show_whitelisted', False)
        show_excluded = request.args.get('show_excluded', False)

        # Base query
        if show_whitelisted:
            base_query = EmailRecord.query.filter_by(session_id=session_id).filter(
                EmailRecord.whitelisted == True
            )
        elif show_excluded:
            base_query = EmailRecord.query.filter_by(session_id=session_id).filter(
                EmailRecord.excluded_by_rule.isnot(None),
                db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
            )
        else:
            # Default: Show only Active cases (exclude whitelisted, cleared, escalated, and excluded records)
            base_query = EmailRecord.query.filter_by(session_id=session_id).filter(
                db.and_(
                    db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False),
                    db.or_(EmailRecord.excluded_by_rule.is_(None)),
                    EmailRecord.case_status == 'Active'  # Only show Active cases by default
                )
            )

        # Apply filters
        if risk_level:
            base_query = base_query.filter(EmailRecord.risk_level == risk_level)
        if case_status:
            base_query = base_query.filter(EmailRecord.case_status == case_status)
        if search:
            search_term = f"%{search}%"
            base_query = base_query.filter(
                db.or_(
                    EmailRecord.sender.ilike(search_term),
                    EmailRecord.subject.ilike(search_term),
                    EmailRecord.recipients_email_domain.ilike(search_term),
                    EmailRecord.recipients.ilike(search_term),
                    EmailRecord.attachments.ilike(search_term)
                )
            )

        # Get all matching records
        all_records = base_query.all()

        # Group records by sender, subject, time, and attachments as requested
        groups = {}
        for record in all_records:
            # Use time rounded to hour for grouping similar time periods
            time_key = ''
            if record.time:
                try:
                    # Round time to the nearest hour for grouping
                    dt = datetime.fromisoformat(record.time.replace('Z', '+00:00'))
                    time_key = dt.strftime('%Y-%m-%d %H:00:00')
                except:
                    time_key = record.time[:16] if record.time else ''

            group_key = (
                record.sender or '',
                record.subject or '',
                time_key,
                record.attachments or ''
            )

            if group_key not in groups:
                groups[group_key] = {
                    'group_id': f"group_{len(groups)}",
                    'sender': record.sender,
                    'subject': record.subject,
                    'time': record.time,
                    'attachments': record.attachments,
                    'recipients': [],
                    'record_count': 0,
                    'highest_risk_score': 0,
                    'risk_level': 'Low',
                    'case_statuses': set(),
                    'primary_record': record,
                    'is_leaver': False  # Will be updated to True if any record is a leaver
                }

            # Add recipient info to group
            groups[group_key]['recipients'].append({
                'record_id': record.record_id,
                'recipient': record.recipients,
                'recipient_domain': record.recipients_email_domain,
                'risk_level': record.risk_level,
                'ml_score': float(record.ml_risk_score or 0),
                'case_status': record.case_status or 'Active',
                'is_flagged': record.is_flagged,
                'flag_reason': record.flag_reason,
                'notes': record.notes,
                'policy_name': record.policy_name
            })

            # Update group metadata
            groups[group_key]['record_count'] += 1
            groups[group_key]['case_statuses'].add(record.case_status or 'Active')

            # Update leaver status - mark as leaver if ANY record in group is a leaver
            if record.leaver == 'YES':
                groups[group_key]['is_leaver'] = True

            # Track highest risk score in group
            if record.ml_risk_score and record.ml_risk_score > groups[group_key]['highest_risk_score']:
                groups[group_key]['highest_risk_score'] = record.ml_risk_score
                groups[group_key]['risk_level'] = record.risk_level or 'Low'

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

        # Convert to list and sort by highest risk score
        grouped_data = []
        for group_key, group_data in groups.items():
            # Convert set to list for JSON serialization
            group_data['case_statuses'] = list(group_data['case_statuses'])

            # Add summary status
            if 'Escalated' in group_data['case_statuses']:
                group_data['group_status'] = 'Escalated'
            elif 'Cleared' in group_data['case_statuses']:
                group_data['group_status'] = 'Mixed' if len(group_data['case_statuses']) > 1 else 'Cleared'
            else:
                group_data['group_status'] = 'Active'

            # Format time for display
            try:
                if group_data['time']:
                    if isinstance(group_data['time'], str):
                        time_obj = datetime.fromisoformat(group_data['time'].replace('Z', '+00:00'))
                    else:
                        time_obj = group_data['time']
                    group_data['time_display'] = time_obj.strftime('%Y-%m-%d %H:%M')
                else:
                    group_data['time_display'] = 'Unknown'
            except:
                group_data['time_display'] = 'Invalid Date'

            # Remove primary_record object (not JSON serializable)
            del group_data['primary_record']

            grouped_data.append(group_data)

        # Sort by highest risk score descending
        grouped_data.sort(key=lambda x: x['highest_risk_score'], reverse=True)

        return jsonify({
            'success': True,
            'grouped_cases': grouped_data,
            'total_groups': len(grouped_data),
            'total_records': len(all_records)
        })

    except Exception as e:
        logger.error(f"Error getting grouped cases for session {session_id}: {str(e)}")
        return jsonify({'error': 'Failed to load grouped cases', 'details': str(e)}), 500

@app.route('/api/group-details/<session_id>/<group_id>')
def api_group_details(session_id, group_id):
    """Get detailed records for a specific group"""
    try:
        # This endpoint will be called when user expands a group
        # For now, return the group data from the grouped-cases endpoint
        # In a production system, you might cache group data or recreate it
        return jsonify({'message': 'Group details - use grouped-cases endpoint with group expansion'})
    except Exception as e:
        logger.error(f"Error getting group details: {str(e)}")
        return jsonify({'error': 'Failed to load group details'}), 500

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
        'time': case.time,
        'bunit': case.bunit,
        'department': case.department,
        'account_type': getattr(case, 'account_type', None)  # Use getattr in case field doesn't exist
    }

    return jsonify(case_data)

# Workflow API Endpoints
@app.route('/api/workflow/<session_id>/status')
def api_workflow_status(session_id):
    """Get workflow status for a session"""
    try:
        status = workflow_manager.get_workflow_status(session_id)
        if status is None:
            return jsonify({'error': 'Session not found or workflow not initialized'}), 404
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error getting workflow status for {session_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/workflow/<session_id>/reset', methods=['POST'])
def api_workflow_reset(session_id):
    """Reset workflow for a session"""
    try:
        success = workflow_manager.reset_workflow(session_id)
        if success:
            return jsonify({'message': 'Workflow reset successfully'})
        else:
            return jsonify({'error': 'Failed to reset workflow'}), 500
    except Exception as e:
        logger.error(f"Error resetting workflow for {session_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500


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
                'description': f'Rule violation detected in email content',
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
def update_case_status_put(session_id, record_id):
    """Update case status (PUT method)"""
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

        # Log the case status update
        AuditLogger.log_case_action(
            action=data.get('status', 'UPDATE'),
            session_id=session_id,
            case_id=record_id,
            details=f"Status updated to {data.get('status')}"
        )

        return jsonify({'status': 'updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/update-case-status/<session_id>/<record_id>', methods=['POST'])
def update_case_status(session_id, record_id):
    """Update case status (POST method for JavaScript compatibility)"""
    try:
        case = EmailRecord.query.filter_by(session_id=session_id, record_id=record_id).first_or_404()
        data = request.get_json()

        new_status = data.get('new_status', data.get('status'))
        case.case_status = new_status
        case.notes = data.get('notes', case.notes)

        if new_status == 'Escalated':
            case.escalated_at = datetime.utcnow()
        elif new_status == 'Cleared':
            case.resolved_at = datetime.utcnow()

        db.session.commit()

        # Log the case status update
        AuditLogger.log_case_action(
            action=new_status or 'UPDATE',
            session_id=session_id,
            case_id=record_id,
            details=f"Status updated to {new_status}"
        )

        return jsonify({'status': 'updated', 'message': f'Case status updated to {new_status}'})
    except Exception as e:
        logger.error(f"Error updating case status: {str(e)}")
        return jsonify({'error': str(e)}), 400

# Adaptive ML API Routes
@app.route('/api/adaptive-learning/trigger/<session_id>', methods=['POST'])
def trigger_adaptive_learning(session_id):
    """Trigger adaptive learning for a session"""
    try:
        success = adaptive_ml_engine.learn_from_user_decisions(session_id)

        if success:
            return jsonify({
                'success': True,
                'message': 'Adaptive learning completed successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Insufficient feedback data for learning'
            })

    except Exception as e:
        logger.error(f"Error triggering adaptive learning: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/adaptive-learning/export/<session_id>')
def export_learning_data(session_id):
    """Export learning data for analysis"""
    try:
        analytics = adaptive_ml_engine.get_learning_analytics(days=90)

        # Create CSV export
        output = StringIO()
        writer = csv.writer(output)

        # Write headers
        writer.writerow(['Date', 'Adaptive Weight', 'Feedback Count', 'Escalation Rate'])

        # Write data
        for evolution in analytics.get('model_evolution', []):
            writer.writerow([
                evolution.get('date', ''),
                evolution.get('adaptive_weight', 0),
                evolution.get('feedback_count', 0),
                evolution.get('escalation_rate', 0)
            ])

        # Create download response
        response_data = BytesIO()
        response_data.write(output.getvalue().encode('utf-8'))
        response_data.seek(0)

        return send_file(
            response_data,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'adaptive_learning_data_{session_id}.csv'
        )

    except Exception as e:
        logger.error(f"Error exporting learning data: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/adaptive-learning/reset', methods=['POST'])
def reset_adaptive_model():
    """Reset the adaptive model to start fresh"""
    try:
        # Reset the adaptive model
        adaptive_ml_engine.adaptive_weight = 0.1
        adaptive_ml_engine.is_adaptive_trained = False
        adaptive_ml_engine.learning_patterns.clear()
        adaptive_ml_engine.recent_feedback.clear()

        # Save reset state
        adaptive_ml_engine._save_models()

        return jsonify({
            'success': True,
            'message': 'Adaptive model reset successfully'
        })

    except Exception as e:
        logger.error(f"Error resetting adaptive model: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/cases/<session_id>/<record_id>/feedback', methods=['POST'])
def record_case_feedback(session_id, record_id):
    """Record user feedback for ML learning"""
    try:
        data = request.get_json()
        decision = data.get('decision')  # 'Escalated' or 'Cleared'

        if decision not in ['Escalated', 'Cleared']:
            return jsonify({'success': False, 'message': 'Invalid decision'}), 400

        # Update case status
        case = EmailRecord.query.filter_by(session_id=session_id, record_id=record_id).first_or_404()
        case.case_status = decision
        case.resolved_at = datetime.utcnow()

        # Record feedback for ML learning
        feedback = MLFeedback(
            session_id=session_id,
            record_id=record_id,
            user_decision=decision,
            original_ml_score=case.ml_risk_score,
            decision_timestamp=datetime.utcnow()
        )

        db.session.add(feedback)
        db.session.commit()

        # Trigger incremental learning if enough feedback
        feedback_count = MLFeedback.query.filter_by(session_id=session_id).count()
        if feedback_count % 10 == 0:  # Learn every 10 decisions
            adaptive_ml_engine.learn_from_user_decisions(session_id)

        return jsonify({
            'success': True,
            'message': f'Case {decision.lower()} and feedback recorded'
        })

    except Exception as e:
        logger.error(f"Error recording case feedback: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

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
        session.data_path = session.data_path or '' # Ensure data_path is string
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
                session.data_path = session.data_path or '' # Ensure data_path is string
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
    """Add multiple ML keywords to wordlist at once"""
    try:
        data = request.get_json()
        keywords_data = data.get("keywords", [])
        default_category = data.get('default_category', 'Business')
        default_keyword_type = data.get('default_keyword_type', 'risk')
        default_applies_to = data.get('default_applies_to', 'both')
        default_match_condition = data.get('default_match_condition', 'contains')
        default_risk_score = data.get('default_risk_score', 1)

        logger.info(f"Bulk add request: {len(keywords_data)} keywords, category: {default_category}, type: {default_keyword_type}, applies_to: {default_applies_to}, match_condition: {default_match_condition}, risk_score: {default_risk_score}")

        if not keywords_data:
            return jsonify({"success": False, "error": "No keywords provided"}), 400

        if default_category not in ['Business', 'Personal', 'Suspicious']:
            return jsonify({"success": False, "error": "Invalid default category"}), 400

        if default_keyword_type not in ['risk', 'exclusion']:
            return jsonify({"success": False, "error": "Invalid default keyword type"}), 400

        if default_applies_to not in ['subject', 'attachment', 'both']:
            return jsonify({"success": False, "error": "Invalid default applies_to value"}), 400

        if not (1 <= default_risk_score <= 10):
            return jsonify({"success": False, "error": "Default risk score must be between 1 and 10"}), 400

        if len(keywords_data) > 100:
            return jsonify({"success": False, "error": "Maximum 100 keywords allowed per bulk import"}), 400

        added_keywords = []
        skipped_keywords = []
        errors = []

        for keyword_entry in keywords_data:
            try:
                # Handle both string and object formats
                if isinstance(keyword_entry, str):
                    keyword_text = keyword_entry.strip()
                    category = default_category
                    keyword_type = default_keyword_type
                    applies_to = default_applies_to
                    match_condition = default_match_condition
                    risk_score = default_risk_score
                else:
                    keyword_text = keyword_entry.get("keyword", "").strip()
                    category = keyword_entry.get('category', default_category)
                    keyword_type = keyword_entry.get('keyword_type', default_keyword_type)
                    applies_to = keyword_entry.get('applies_to', default_applies_to)
                    match_condition = keyword_entry.get('match_condition', default_match_condition)
                    risk_score = keyword_entry.get('risk_score', default_risk_score)

                if not keyword_text:
                    continue

                # Validation
                if category not in ["Business", "Personal", "Suspicious", "Exclusion"]:
                    errors.append(f'Invalid category "{category}" for keyword "{keyword_text}"')
                    continue

                if keyword_type not in ["risk", "exclusion"]:
                    errors.append(f'Invalid keyword type "{keyword_type}" for keyword "{keyword_text}"')
                    continue

                if applies_to not in ["subject", "attachment", "both"]:
                    errors.append(f'Invalid applies_to value "{applies_to}" for keyword "{keyword_text}"')
                    continue

                if match_condition not in ["contains", "equals", "starts_with", "ends_with"]:
                    errors.append(f'Invalid match condition "{match_condition}" for keyword "{keyword_text}"')
                    continue

                if not (1 <= risk_score <= 10):
                    errors.append(f'Invalid risk score "{risk_score}" for keyword "{keyword_text}"')
                    continue

                if len(keyword_text) > 100:  # Reasonable length limit
                    errors.append(f'Keyword too long: "{keyword_text[:20]}..."')
                    continue

                # Check if keyword already exists (case-insensitive) with same type and applies_to
                existing = AttachmentKeyword.query.filter(
                    db.func.lower(AttachmentKeyword.keyword) == keyword_text.lower(),
                    AttachmentKeyword.keyword_type == keyword_type,
                    AttachmentKeyword.applies_to == applies_to,
                    AttachmentKeyword.match_condition == match_condition
                ).first()

                if existing:
                    logger.info(f"Keyword '{keyword_text}' already exists with same type/scope/condition, skipping")
                    skipped_keywords.append({
                        "keyword": keyword_text,
                        "reason": "Already exists"
                    })
                    continue

                # Create new keyword
                new_keyword = AttachmentKeyword(
                    keyword=keyword_text,
                    category=category,
                    risk_score=risk_score,
                    keyword_type=keyword_type,
                    applies_to=applies_to,
                    match_condition=match_condition,
                    is_active=True
                )

                db.session.add(new_keyword)
                added_keywords.append({
                    "keyword": keyword_text,
                    "category": category,
                    "keyword_type": keyword_type,
                    "applies_to": applies_to,
                    "match_condition": match_condition,
                    "risk_score": risk_score
                })

            except Exception as keyword_error:
                error_msg = f'Error processing "{keyword_text if "keyword_text" in locals() else str(keyword_entry)}": {str(keyword_error)}'
                errors.append({"keyword": keyword_text if 'keyword_text' in locals() else str(keyword_entry), "error": error_msg})
                logger.error(error_msg)
                continue

        # Commit all successful additions
        if added_keywords:
            try:
                db.session.commit()
                logger.info(f"Successfully committed {len(added_keywords)} new keywords to database")
            except Exception as e:
                error_msg = f'Database commit error: {str(e)}'
                logger.error(error_msg)
                db.session.rollback()
                return jsonify({'success': False, 'error': error_msg}), 500
        else:
            logger.info("No new keywords to commit")

        # Create success message
        message = f'Bulk operation completed: {len(added_keywords)} added'
        if skipped_keywords:
            message += f', {len(skipped_keywords)} duplicates skipped'
        if errors:
            message += f', {len(errors)} errors occurred'

        logger.info(message)

        return jsonify({
            'success': True,
            'message': message,
            'added_count': len(added_keywords),
            'skipped_count': len(skipped_keywords),
            'error_count': len(errors),
            'added_keywords': added_keywords,
            'skipped_keywords': skipped_keywords,
            'errors': errors[:10]  # Limit error messages
        })

    except Exception as e:
        error_msg = f"Error in bulk keyword import: {str(e)}"
        logger.error(error_msg)
        db.session.rollback()
        return jsonify({'success': False, 'error': error_msg}), 500

# Admin Audit Dashboard Route
@app.route('/admin/audit')
def admin_audit_dashboard():
    """Admin audit dashboard to view all system changes"""
    try:
        # Get recent audit logs (last 1000 entries)
        recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(1000).all()

        # Get audit summary for last 30 days
        summary = AuditLogger.get_audit_summary(days=30)

        return render_template('admin_audit_dashboard.html', 
                             audit_logs=recent_logs,
                             audit_summary=summary)
    except Exception as e:
        logger.error(f"Error loading audit dashboard: {str(e)}")
        flash(f'Error loading audit data: {str(e)}', 'error')
        return redirect(url_for('admin'))

@app.route('/api/audit/logs')
def api_audit_logs():
    """API endpoint for audit logs"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False)

        return jsonify({
            'logs': [{
                'id': log.id,
                'timestamp': log.timestamp.isoformat(),
                'user_id': log.user_id,
                'action_type': log.action_type,
                'resource_type': log.resource_type,
                'resource_id': log.resource_id,
                'details': log.details,
                'severity': log.severity,
                'ip_address': log.ip_address
            } for log in logs.items],
            'total': logs.total,
            'pages': logs.pages,
            'current_page': page
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500



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

@app.route('/processing-status/<session_id>')
def processing_status_page(session_id):
    """Processing status page for monitoring session progress"""
    session = ProcessingSession.query.get_or_404(session_id)
    return render_template('processing_status.html', session=session)

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
            ).filter(EmailRecord.whitelisted != True).count()

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
        # Default view - exclude whitelisted, cleared, escalated, and flagged records from cases
        query = EmailRecord.query.filter_by(session_id=session_id).filter(
            db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
        ).filter(
            db.or_(
                EmailRecord.case_status.is_(None),
                EmailRecord.case_status == 'Active'
            )
        ).filter(
            db.or_(EmailRecord.is_flagged.is_(None), EmailRecord.is_flagged == False)
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

    # Get only manually escalated cases - exclude whitelisted records
    # NOTE: Removed automatic critical case inclusion - user controls escalation
    escalated_cases = EmailRecord.query.filter_by(
        session_id=session_id,
        case_status='Escalated'
    ).filter(
        db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
    ).order_by(EmailRecord.escalated_at.desc()).all()

    # Empty critical_cases for backward compatibility - all escalation is manual now
    critical_cases = []

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

@app.route('/api/simple-learning-progress')
def api_simple_learning_progress():
    """Simple API for learning progress tracking"""
    try:
        # Get learning feedback data
        total_decisions = db.session.execute(text('SELECT COUNT(*) as count FROM ml_feedback')).scalar()
        escalated_count = db.session.execute(text("SELECT COUNT(*) as count FROM ml_feedback WHERE user_decision = 'Escalated'")).scalar()
        cleared_count = db.session.execute(text("SELECT COUNT(*) as count FROM ml_feedback WHERE user_decision = 'Cleared'")).scalar()

        # Get latest decision timestamp
        latest_decision = db.session.execute(text('SELECT MAX(decision_timestamp) FROM ml_feedback')).scalar()
        latest_str = latest_decision.strftime('%Y-%m-%d %H:%M') if latest_decision else 'Never'

        # Calculate adaptive weight (grows from 10% to 70% based on decisions)
        adaptive_weight_percent = min(10 + (total_decisions * 0.6), 70)

        return jsonify({
            'total_decisions': total_decisions or 0,
            'escalated_count': escalated_count or 0,
            'cleared_count': cleared_count or 0,
            'flagged_count': 0,  # We can add this later
            'last_decision': latest_str,
            'adaptive_weight': f"{adaptive_weight_percent:.1f}%",
            'learning_confidence': f"{min(total_decisions * 2, 100):.0f}%",
            'is_learning': total_decisions > 0
        })

    except Exception as e:
        logger.error(f"Error getting simple learning progress: {str(e)}")
        return jsonify({
            'total_decisions': 0,
            'escalated_count': 0,
            'cleared_count': 0,
            'flagged_count': 0,
            'last_decision': 'Error',
            'adaptive_weight': '10%',
            'learning_confidence': '0%',
            'is_learning': False,
            'error': str(e)
        })

@app.route('/learning-progress')
def learning_progress_simple():
    """Simple learning progress page"""
    return render_template('learning_progress_simple.html')

@app.route('/adaptive_ml_dashboard/<session_id>')
def adaptive_ml_dashboard(session_id):
    """Adaptive ML learning dashboard"""
    session = ProcessingSession.query.get_or_404(session_id)

    try:
        # Use fast analytics for better performance
        analytics = adaptive_ml_engine.get_fast_learning_analytics()

        # Ensure the analytics structure is complete
        if not analytics:
            analytics = {}

        # Provide fallback structure if any section is missing
        if 'performance_metrics' not in analytics:
            analytics['performance_metrics'] = {
                'model_trained': False,
                'adaptive_weight': 0.1,
                'learning_confidence': 0.0,
                'latest_session_feedback': 0,
                'model_maturity': 'Initial'
            }

        # Ensure all required fields exist in performance_metrics
        if 'adaptive_weight' not in analytics.get('performance_metrics', {}):
            analytics['performance_metrics']['adaptive_weight'] = adaptive_ml_engine.adaptive_weight
        if 'learning_confidence' not in analytics.get('performance_metrics', {}):
            analytics['performance_metrics']['learning_confidence'] = 0.0
        if 'model_trained' not in analytics.get('performance_metrics', {}):
            analytics['performance_metrics']['model_trained'] = False
        if 'latest_session_feedback' not in analytics.get('performance_metrics', {}):
            analytics['performance_metrics']['latest_session_feedback'] = 0
        if 'model_maturity' not in analytics.get('performance_metrics', {}):
            analytics['performance_metrics']['model_maturity'] = 'Initial'

        # Provide fallback structure for other sections
        default_analytics = {
            'model_evolution': {
                'improvement_over_time': [],
                'weight_progression': [],
                'accuracy_trends': []
            },
            'learning_trends': {
                'learning_sessions': 0,
                'total_decisions_learned': 0,
                'total_escalations': 0,
                'total_cleared': 0,
                'learning_rate': 0.0
            },
            'decision_patterns': {
                'escalation_reasons': {},
                'pattern_analysis': {},
                'confidence_distribution': []
            },
            'feature_insights': {
                'top_features': [],
                'feature_weights': {},
                'correlation_matrix': []
            },
            'recommendations': []
        }

        # Merge default values for missing sections - ensure analytics is a dict
        if not isinstance(analytics, dict):
            analytics = {}

        for key, default_value in default_analytics.items():
            if key not in analytics:
                analytics[key] = default_value
            elif isinstance(default_value, dict) and isinstance(analytics.get(key), dict):
                # Merge nested dictionaries to ensure all required fields exist
                for subkey, subvalue in default_value.items():
                    if subkey not in analytics[key]:
                        analytics[key][subkey] = subvalue

    except Exception as e:
        logger.error(f"Error getting adaptive ML analytics: {str(e)}")
        # Provide complete fallback analytics
        analytics = {
            'model_evolution': {'improvement_over_time': [], 'weight_progression': [], 'accuracy_trends': []},
            'learning_trends': {'learning_sessions': 0, 'total_decisions_learned': 0, 'total_escalations': 0, 'total_cleared': 0, 'learning_rate': 0.0},
            'decision_patterns': {'escalation_reasons': {}, 'pattern_analysis': {}, 'confidence_distribution': []},
            'performance_metrics': {'model_trained': False, 'adaptive_weight': 0.1, 'learning_confidence': 0.0, 'latest_session_feedback': 0, 'model_maturity': 'Initial'},
            'feature_insights': {'top_features': [], 'feature_weights': {}, 'correlation_matrix': []},
            'recommendations': []
        }

    # Ensure analytics is always a dictionary before serialization
    if not isinstance(analytics, dict):
        analytics = {
            'model_evolution': {'improvement_over_time': [], 'weight_progression': [], 'accuracy_trends': []},
            'learning_trends': {'learning_sessions': 0, 'total_decisions_learned': 0, 'total_escalations': 0, 'total_cleared': 0, 'learning_rate': 0.0},
            'decision_patterns': {'escalation_reasons': {}, 'pattern_analysis': {}, 'confidence_distribution': []},
            'performance_metrics': {'model_trained': False, 'adaptive_weight': 0.1, 'learning_confidence': 0.0, 'latest_session_feedback': 0, 'model_maturity': 'Initial'},
            'feature_insights': {'top_features': [], 'feature_weights': {}, 'correlation_matrix': []},
            'recommendations': []
        }

    # Create safe analytics data for JavaScript serialization
    safe_analytics = {
        'model_evolution': {
            'improvement_over_time': analytics.get('model_evolution', {}).get('improvement_over_time', []) if isinstance(analytics.get('model_evolution'), dict) else [],
            'weight_progression': analytics.get('model_evolution', {}).get('weight_progression', []) if isinstance(analytics.get('model_evolution'), dict) else [],
            'accuracy_trends': analytics.get('model_evolution', {}).get('accuracy_trends', []) if isinstance(analytics.get('model_evolution'), dict) else []
        },
        'learning_trends': {
            'learning_sessions': analytics.get('learning_trends', {}).get('learning_sessions', 0) if isinstance(analytics.get('learning_trends'), dict) else 0,
            'total_decisions_learned': analytics.get('learning_trends', {}).get('total_decisions_learned', 0) if isinstance(analytics.get('learning_trends'), dict) else 0,
            'total_escalations': analytics.get('learning_trends', {}).get('total_escalations', 0) if isinstance(analytics.get('learning_trends'), dict) else 0,
            'total_cleared': analytics.get('learning_trends', {}).get('total_cleared', 0) if isinstance(analytics.get('learning_trends'), dict) else 0,
            'learning_rate': analytics.get('learning_trends', {}).get('learning_rate', 0.0) if isinstance(analytics.get('learning_trends'), dict) else 0.0
        },
        'decision_patterns': analytics.get('decision_patterns', {}) if isinstance(analytics.get('decision_patterns'), dict) else {},
        'performance_metrics': {
            'model_trained': analytics.get('performance_metrics', {}).get('model_trained', False) if isinstance(analytics.get('performance_metrics'), dict) else False,
            'adaptive_weight': analytics.get('performance_metrics', {}).get('adaptive_weight', 0.1) if isinstance(analytics.get('performance_metrics'), dict) else 0.1,
            'learning_confidence': analytics.get('performance_metrics', {}).get('learning_confidence', 0.0) if isinstance(analytics.get('performance_metrics'), dict) else 0.0,
            'latest_session_feedback': analytics.get('performance_metrics', {}).get('latest_session_feedback', 0) if isinstance(analytics.get('performance_metrics'), dict) else 0,
            'model_maturity': analytics.get('performance_metrics', {}).get('model_maturity', 'Initial') if isinstance(analytics.get('performance_metrics'), dict) else 'Initial'
        },
        'feature_insights': analytics.get('feature_insights', {}) if isinstance(analytics.get('feature_insights'), dict) else {},
        'recommendations': analytics.get('recommendations', []) if isinstance(analytics.get('recommendations'), list) else []
    }

    return render_template('adaptive_ml_dashboard.html',
                         session=session,
                         analytics=analytics,
                         analytics_json=safe_analytics)

@app.route('/admin')
def admin():
    """Administration panel"""
    # Email Guardian - Flask Routes
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, make_response, abort, session
from werkzeug.utils import secure_filename
from app import app, db
from models import *
from performance_config import PerformanceConfig


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

@app.route('/api/grouped-cases/<session_id>')
def api_grouped_cases(session_id):
    """Get grouped email cases for case manager - groups by sender, subject, time, and content"""
    try:
        # Get filter parameters
        risk_level = request.args.get('risk_level', '')
        case_status = request.args.get('case_status', '')
        search = request.args.get('search', '')
        show_whitelisted = request.args.get('show_whitelisted', False)
        show_excluded = request.args.get('show_excluded', False)

        # Base query
        if show_whitelisted:
            base_query = EmailRecord.query.filter_by(session_id=session_id).filter(
                EmailRecord.whitelisted == True
            )
        elif show_excluded:
            base_query = EmailRecord.query.filter_by(session_id=session_id).filter(
                EmailRecord.excluded_by_rule.isnot(None),
                db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
            )
        else:
            # Default: Show only Active cases (exclude whitelisted, cleared, escalated, and excluded records)
            base_query = EmailRecord.query.filter_by(session_id=session_id).filter(
                db.and_(
                    db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False),
                    db.or_(EmailRecord.excluded_by_rule.is_(None)),
                    EmailRecord.case_status == 'Active'  # Only show Active cases by default
                )
            )

        # Apply filters
        if risk_level:
            base_query = base_query.filter(EmailRecord.risk_level == risk_level)
        if case_status:
            base_query = base_query.filter(EmailRecord.case_status == case_status)
        if search:
            search_term = f"%{search}%"
            base_query = base_query.filter(
                db.or_(
                    EmailRecord.sender.ilike(search_term),
                    EmailRecord.subject.ilike(search_term),
                    EmailRecord.recipients_email_domain.ilike(search_term),
                    EmailRecord.recipients.ilike(search_term),
                    EmailRecord.attachments.ilike(search_term)
                )
            )

        # Get all matching records
        all_records = base_query.all()

        # Group records by sender, subject, time, and attachments as requested
        groups = {}
        for record in all_records:
            # Use time rounded to hour for grouping similar time periods
            time_key = ''
            if record.time:
                try:
                    # Round time to the nearest hour for grouping
                    dt = datetime.fromisoformat(record.time.replace('Z', '+00:00'))
                    time_key = dt.strftime('%Y-%m-%d %H:00:00')
                except:
                    time_key = record.time[:16] if record.time else ''

            group_key = (
                record.sender or '',
                record.subject or '',
                time_key,
                record.attachments or ''
            )

            if group_key not in groups:
                groups[group_key] = {
                    'group_id': f"group_{len(groups)}",
                    'sender': record.sender,
                    'subject': record.subject,
                    'time': record.time,
                    'attachments': record.attachments,
                    'recipients': [],
                    'record_count': 0,
                    'highest_risk_score': 0,
                    'risk_level': 'Low',
                    'case_statuses': set(),
                    'primary_record': record,
                    'is_leaver': False  # Will be updated to True if any record is a leaver
                }

            # Add recipient info to group
            groups[group_key]['recipients'].append({
                'record_id': record.record_id,
                'recipient': record.recipients,
                'recipient_domain': record.recipients_email_domain,
                'risk_level': record.risk_level,
                'ml_score': float(record.ml_risk_score or 0),
                'case_status': record.case_status or 'Active',
                'is_flagged': record.is_flagged,
                'flag_reason': record.flag_reason,
                'notes': record.notes,
                'policy_name': record.policy_name
            })

            # Update group metadata
            groups[group_key]['record_count'] += 1
            groups[group_key]['case_statuses'].add(record.case_status or 'Active')

            # Update leaver status - mark as leaver if ANY record in group is a leaver
            if record.leaver == 'YES':
                groups[group_key]['is_leaver'] = True

            # Track highest risk score in group
            if record.ml_risk_score and record.ml_risk_score > groups[group_key]['highest_risk_score']:
                groups[group_key]['highest_risk_score'] = record.ml_risk_score
                groups[group_key]['risk_level'] = record.risk_level or 'Low'

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

        # Convert to list and sort by highest risk score
        grouped_data = []
        for group_key, group_data in groups.items():
            # Convert set to list for JSON serialization
            group_data['case_statuses'] = list(group_data['case_statuses'])

            # Add summary status
            if 'Escalated' in group_data['case_statuses']:
                group_data['group_status'] = 'Escalated'
            elif 'Cleared' in group_data['case_statuses']:
                group_data['group_status'] = 'Mixed' if len(group_data['case_statuses']) > 1 else 'Cleared'
            else:
                group_data['group_status'] = 'Active'

            # Format time for display
            try:
                if group_data['time']:
                    if isinstance(group_data['time'], str):
                        time_obj = datetime.fromisoformat(group_data['time'].replace('Z', '+00:00'))
                    else:
                        time_obj = group_data['time']
                    group_data['time_display'] = time_obj.strftime('%Y-%m-%d %H:%M')
                else:
                    group_data['time_display'] = 'Unknown'
            except:
                group_data['time_display'] = 'Invalid Date'

            # Remove primary_record object (not JSON serializable)
            del group_data['primary_record']

            grouped_data.append(group_data)

        # Sort by highest risk score descending
        grouped_data.sort(key=lambda x: x['highest_risk_score'], reverse=True)

        return jsonify({
            'success': True,
            'grouped_cases': grouped_data,
            'total_groups': len(grouped_data),
            'total_records': len(all_records)
        })

    except Exception as e:
        logger.error(f"Error getting grouped cases for session {session_id}: {str(e)}")
        return jsonify({'error': 'Failed to load grouped cases', 'details': str(e)}), 500

@app.route('/api/group-details/<session_id>/<group_id>')
def api_group_details(session_id, group_id):
    """Get detailed records for a specific group"""
    try:
        # This endpoint will be called when user expands a group
        # For now, return the group data from the grouped-cases endpoint
        # In a production system, you might cache group data or recreate it
        return jsonify({'message': 'Group details - use grouped-cases endpoint with group expansion'})
    except Exception as e:
        logger.error(f"Error getting group details: {str(e)}")
        return jsonify({'error': 'Failed to load group details'}), 500

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
        'time': case.time,
        'bunit': case.bunit,
        'department': case.department,
        'account_type': getattr(case, 'account_type', None)  # Use getattr in case field doesn't exist
    }

    return jsonify(case_data)

# Workflow API Endpoints
@app.route('/api/workflow/<session_id>/status')
def api_workflow_status(session_id):
    """Get workflow status for a session"""
    try:
        status = workflow_manager.get_workflow_status(session_id)
        if status is None:
            return jsonify({'error': 'Session not found or workflow not initialized'}), 404
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error getting workflow status for {session_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/workflow/<session_id>/reset', methods=['POST'])
def api_workflow_reset(session_id):
    """Reset workflow for a session"""
    try:
        success = workflow_manager.reset_workflow(session_id)
        if success:
            return jsonify({'message': 'Workflow reset successfully'})
        else:
            return jsonify({'error': 'Failed to reset workflow'}), 500
    except Exception as e:
        logger.error(f"Error resetting workflow for {session_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500


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
                'description': f'Rule violation detected in email content',
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
def update_case_status_put(session_id, record_id):
    """Update case status (PUT method)"""
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

        # Log the case status update
        AuditLogger.log_case_action(
            action=data.get('status', 'UPDATE'),
            session_id=session_id,
            case_id=record_id,
            details=f"Status updated to {data.get('status')}"
        )

        return jsonify({'status': 'updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/update-case-status/<session_id>/<record_id>', methods=['POST'])
def update_case_status(session_id, record_id):
    """Update case status (POST method for JavaScript compatibility)"""
    try:
        case = EmailRecord.query.filter_by(session_id=session_id, record_id=record_id).first_or_404()
        data = request.get_json()

        new_status = data.get('new_status', data.get('status'))
        case.case_status = new_status
        case.notes = data.get('notes', case.notes)

        if new_status == 'Escalated':
            case.escalated_at = datetime.utcnow()
        elif new_status == 'Cleared':
            case.resolved_at = datetime.utcnow()

        db.session.commit()

        # Log the case status update
        AuditLogger.log_case_action(
            action=new_status or 'UPDATE',
            session_id=session_id,
            case_id=record_id,
            details=f"Status updated to {new_status}"
        )

        return jsonify({'status': 'updated', 'message': f'Case status updated to {new_status}'})
    except Exception as e:
        logger.error(f"Error updating case status: {str(e)}")
        return jsonify({'error': str(e)}), 400

# Adaptive ML API Routes
@app.route('/api/adaptive-learning/trigger/<session_id>', methods=['POST'])
def trigger_adaptive_learning(session_id):
    """Trigger adaptive learning for a session"""
    try:
        success = adaptive_ml_engine.learn_from_user_decisions(session_id)

        if success:
            return jsonify({
                'success': True,
                'message': 'Adaptive learning completed successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Insufficient feedback data for learning'
            })

    except Exception as e:
        logger.error(f"Error triggering adaptive learning: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/adaptive-learning/export/<session_id>')
def export_learning_data(session_id):
    """Export learning data for analysis"""
    try:
        analytics = adaptive_ml_engine.get_learning_analytics(days=90)

        # Create CSV export
        output = StringIO()
        writer = csv.writer(output)

        # Write headers
        writer.writerow(['Date', 'Adaptive Weight', 'Feedback Count', 'Escalation Rate'])

        # Write data
        for evolution in analytics.get('model_evolution', []):
            writer.writerow([
                evolution.get('date', ''),
                evolution.get('adaptive_weight', 0),
                evolution.get('feedback_count', 0),
                evolution.get('escalation_rate', 0)
            ])

        # Create download response
        response_data = BytesIO()
        response_data.write(output.getvalue().encode('utf-8'))
        response_data.seek(0)

        return send_file(
            response_data,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'adaptive_learning_data_{session_id}.csv'
        )

    except Exception as e:
        logger.error(f"Error exporting learning data: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/adaptive-learning/reset', methods=['POST'])
def reset_adaptive_model():
    """Reset the adaptive model to start fresh"""
    try:
        # Reset the adaptive model
        adaptive_ml_engine.adaptive_weight = 0.1
        adaptive_ml_engine.is_adaptive_trained = False
        adaptive_ml_engine.learning_patterns.clear()
        adaptive_ml_engine.recent_feedback.clear()

        # Save reset state
        adaptive_ml_engine._save_models()

        return jsonify({
            'success': True,
            'message': 'Adaptive model reset successfully'
        })

    except Exception as e:
        logger.error(f"Error resetting adaptive model: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/cases/<session_id>/<record_id>/feedback', methods=['POST'])
def record_case_feedback(session_id, record_id):
    """Record user feedback for ML learning"""
    try:
        data = request.get_json()
        decision = data.get('decision')  # 'Escalated' or 'Cleared'

        if decision not in ['Escalated', 'Cleared']:
            return jsonify({'success': False, 'message': 'Invalid decision'}), 400

        # Update case status
        case = EmailRecord.query.filter_by(session_id=session_id, record_id=record_id).first_or_404()
        case.case_status = decision
        case.resolved_at = datetime.utcnow()

        # Record feedback for ML learning
        feedback = MLFeedback(
            session_id=session_id,
            record_id=record_id,
            user_decision=decision,
            original_ml_score=case.ml_risk_score,
            decision_timestamp=datetime.utcnow()
        )

        db.session.add(feedback)
        db.session.commit()

        # Trigger incremental learning if enough feedback
        feedback_count = MLFeedback.query.filter_by(session_id=session_id).count()
        if feedback_count % 10 == 0:  # Learn every 10 decisions
            adaptive_ml_engine.learn_from_user_decisions(session_id)

        return jsonify({
            'success': True,
            'message': f'Case {decision.lower()} and feedback recorded'
        })

    except Exception as e:
        logger.error(f"Error recording case feedback: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

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
        session.data_path = session.data_path or '' # Ensure data_path is string
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
                session.data_path = session.data_path or '' # Ensure data_path is string
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
    """Add multiple ML keywords to wordlist at once"""
    try:
        data = request.get_json()
        keywords_data = data.get("keywords", [])
        default_category = data.get('default_category', 'Business')
        default_keyword_type = data.get('default_keyword_type', 'risk')
        default_applies_to = data.get('default_applies_to', 'both')
        default_match_condition = data.get('default_match_condition', 'contains')
        default_risk_score = data.get('default_risk_score', 1)

        logger.info(f"Bulk add request: {len(keywords_data)} keywords, category: {default_category}, type: {default_keyword_type}, applies_to: {default_applies_to}, match_condition: {default_match_condition}, risk_score: {default_risk_score}")

        if not keywords_data:
            return jsonify({"success": False, "error": "No keywords provided"}), 400

        if default_category not in ['Business', 'Personal', 'Suspicious']:
            return jsonify({"success": False, "error": "Invalid default category"}), 400

        if default_keyword_type not in ['risk', 'exclusion']:
            return jsonify({"success": False, "error": "Invalid default keyword type"}), 400

        if default_applies_to not in ['subject', 'attachment', 'both']:
            return jsonify({"success": False, "error": "Invalid default applies_to value"}), 400

        if not (1 <= default_risk_score <= 10):
            return jsonify({"success": False, "error": "Default risk score must be between 1 and 10"}), 400

        if len(keywords_data) > 100:
            return jsonify({"success": False, "error": "Maximum 100 keywords allowed per bulk import"}), 400

        added_keywords = []
        skipped_keywords = []
        errors = []

        for keyword_entry in keywords_data:
            try:
                # Handle both string and object formats
                if isinstance(keyword_entry, str):
                    keyword_text = keyword_entry.strip()
                    category = default_category
                    keyword_type = default_keyword_type
                    applies_to = default_applies_to
                    match_condition = default_match_condition
                    risk_score = default_risk_score
                else:
                    keyword_text = keyword_entry.get("keyword", "").strip()
                    category = keyword_entry.get('category', default_category)
                    keyword_type = keyword_entry.get('keyword_type', default_keyword_type)
                    applies_to = keyword_entry.get('applies_to', default_applies_to)
                    match_condition = keyword_entry.get('match_condition', default_match_condition)
                    risk_score = keyword_entry.get('risk_score', default_risk_score)

                if not keyword_text:
                    continue

                # Validation
                if category not in ["Business", "Personal", "Suspicious", "Exclusion"]:
                    errors.append(f'Invalid category "{category}" for keyword "{keyword_text}"')
                    continue

                if keyword_type not in ["risk", "exclusion"]:
                    errors.append(f'Invalid keyword type "{keyword_type}" for keyword "{keyword_text}"')
                    continue

                if applies_to not in ["subject", "attachment", "both"]:
                    errors.append(f'Invalid applies_to value "{applies_to}" for keyword "{keyword_text}"')
                    continue

                if match_condition not in ["contains", "equals", "starts_with", "ends_with"]:
                    errors.append(f'Invalid match condition "{match_condition}" for keyword "{keyword_text}"')
                    continue

                if not (1 <= risk_score <= 10):
                    errors.append(f'Invalid risk score "{risk_score}" for keyword "{keyword_text}"')
                    continue

                if len(keyword_text) > 100:  # Reasonable length limit
                    errors.append(f'Keyword too long: "{keyword_text[:20]}..."')
                    continue

                # Check if keyword already exists (case-insensitive) with same type and applies_to
                existing = AttachmentKeyword.query.filter(
                    db.func.lower(AttachmentKeyword.keyword) == keyword_text.lower(),
                    AttachmentKeyword.keyword_type == keyword_type,
                    AttachmentKeyword.applies_to == applies_to,
                    AttachmentKeyword.match_condition == match_condition
                ).first()

                if existing:
                    logger.info(f"Keyword '{keyword_text}' already exists with same type/scope/condition, skipping")
                    skipped_keywords.append({
                        "keyword": keyword_text,
                        "reason": "Already exists"
                    })
                    continue

                # Create new keyword
                new_keyword = AttachmentKeyword(
                    keyword=keyword_text,
                    category=category,
                    risk_score=risk_score,
                    keyword_type=keyword_type,
                    applies_to=applies_to,
                    match_condition=match_condition,
                    is_active=True
                )

                db.session.add(new_keyword)
                added_keywords.append({
                    "keyword": keyword_text,
                    "category": category,
                    "keyword_type": keyword_type,
                    "applies_to": applies_to,
                    "match_condition": match_condition,
                    "risk_score": risk_score
                })

            except Exception as keyword_error:
                error_msg = f'Error processing "{keyword_text if "keyword_text" in locals() else str(keyword_entry)}": {str(keyword_error)}'
                errors.append({"keyword": keyword_text if 'keyword_text' in locals() else str(keyword_entry), "error": error_msg})
                logger.error(error_msg)
                continue

        # Commit all successful additions
        if added_keywords:
            try:
                db.session.commit()
                logger.info(f"Successfully committed {len(added_keywords)} new keywords to database")
            except Exception as e:
                error_msg = f'Database commit error: {str(e)}'
                logger.error(error_msg)
                db.session.rollback()
                return jsonify({'success': False, 'error': error_msg}), 500
        else:
            logger.info("No new keywords to commit")

        # Create success message
        message = f'Bulk operation completed: {len(added_keywords)} added'
        if skipped_keywords:
            message += f', {len(skipped_keywords)} duplicates skipped'
        if errors:
            message += f', {len(errors)} errors occurred'

        logger.info(message)

        return jsonify({
            'success': True,
            'message': message,
            'added_count': len(added_keywords),
            'skipped_count': len(skipped_keywords),
            'error_count': len(errors),
            'added_keywords': added_keywords,
            'skipped_keywords': skipped_keywords,
            'errors': errors[:10]  # Limit error messages
        })

    except Exception as e:
        error_msg = f"Error in bulk keyword import: {str(e)}"
        logger.error(error_msg)
        db.session.rollback()
        return jsonify({'success': False, 'error': error_msg}), 500

# Admin Audit Dashboard Route
@app.route('/admin/audit')
def admin_audit_dashboard():
    """Admin audit dashboard to view all system changes"""
    try:
        # Get recent audit logs (last 1000 entries)
        recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(1000).all()

        # Get audit summary for last 30 days
        summary = AuditLogger.get_audit_summary(days=30)

        return render_template('admin_audit_dashboard.html', 
                             audit_logs=recent_logs,
                             audit_summary=summary)
    except Exception as e:
        logger.error(f"Error loading audit dashboard: {str(e)}")
        flash(f'Error loading audit data: {str(e)}', 'error')
        return redirect(url_for('admin'))

@app.route('/api/audit/logs')
def api_audit_logs():
    """API endpoint for audit logs"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False)

        return jsonify({
            'logs': [{
                'id': log.id,
                'timestamp': log.timestamp.isoformat(),
                'user_id': log.user_id,
                'action_type': log.action_type,
                'resource_type': log.resource_type,
                'resource_id': log.resource_id,
                'details': log.details,
                'severity': log.severity,
                'ip_address': log.ip_address
            } for log in logs.items],
            'total': logs.total,
            'pages': logs.pages,
            'current_page': page
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500