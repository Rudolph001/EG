#!/usr/bin/env python3
"""
Demo script to showcase the Adaptive ML Learning capabilities
"""

import os
import sys
sys.path.append('.')

from app import app, db
from models import ProcessingSession, EmailRecord, MLFeedback, AdaptiveLearningMetrics
from adaptive_ml_engine import AdaptiveMLEngine
import random
from datetime import datetime, timedelta
import uuid

def create_demo_session():
    """Create a demo session with sample email records"""
    print("Creating demo session with sample data...")
    
    # Create demo session
    session_id = str(uuid.uuid4())
    session = ProcessingSession(
        id=session_id,
        filename="adaptive_learning_demo.csv",
        status='completed',
        total_records=50,
        processed_records=50,
        upload_time=datetime.utcnow() - timedelta(hours=2)
    )
    db.session.add(session)
    db.session.commit()  # Commit session first to satisfy foreign key constraint
    
    # Create sample email records with varied risk patterns
    sample_emails = [
        # High-risk patterns (should be escalated)
        {"sender": "external@suspicious-domain.com", "subject": "URGENT: Invoice Payment Required", 
         "attachments": "invoice.exe, payment_details.pdf", "leaver": "Yes", "risk_type": "high"},
        {"sender": "finance@fake-company.org", "subject": "Wire Transfer Authorization", 
         "attachments": "transfer_form.zip", "leaver": "No", "risk_type": "high"},
        {"sender": "admin@phishing-site.net", "subject": "Account Suspended - Immediate Action Required", 
         "attachments": "account_recovery.scr", "leaver": "No", "risk_type": "high"},
        
        # Medium-risk patterns (mixed decisions expected)
        {"sender": "colleague@company.com", "subject": "Confidential Document Review", 
         "attachments": "confidential_report.pdf", "leaver": "Yes", "risk_type": "medium"},
        {"sender": "partner@trusted-vendor.com", "subject": "Contract Amendment", 
         "attachments": "contract_v2.docx", "leaver": "No", "risk_type": "medium"},
        
        # Low-risk patterns (should be cleared)
        {"sender": "team@company.com", "subject": "Weekly Team Meeting Notes", 
         "attachments": "meeting_notes.pdf", "leaver": "No", "risk_type": "low"},
        {"sender": "hr@company.com", "subject": "Employee Handbook Update", 
         "attachments": "handbook_2024.pdf", "leaver": "No", "risk_type": "low"},
    ]
    
    # Generate multiple instances of each pattern
    records = []
    for i in range(50):
        base_email = sample_emails[i % len(sample_emails)]
        record = EmailRecord(
            session_id=session_id,
            record_id=f"demo_{i+1}",
            sender=f"{base_email['sender'].split('@')[0]}{random.randint(1,999)}@{base_email['sender'].split('@')[1]}",
            subject=base_email['subject'] + f" #{random.randint(100,999)}",
            attachments=base_email['attachments'],
            recipients="user@company.com",
            recipients_email_domain="company.com",
            leaver=base_email['leaver'],
            time=f"2024-08-{random.randint(1,30):02d}T{random.randint(9,17):02d}:{random.randint(0,59):02d}:00",
            ml_risk_score=random.uniform(0.1, 0.9),
            risk_level=base_email['risk_type'].title(),
            case_status='Active'
        )
        records.append(record)
        db.session.add(record)
    
    db.session.commit()
    print(f"✓ Created demo session {session_id} with {len(records)} sample records")
    return session_id

def simulate_user_decisions(session_id, adaptive_engine):
    """Simulate realistic user escalation/clear decisions"""
    print("Simulating user decisions based on risk patterns...")
    
    records = EmailRecord.query.filter_by(session_id=session_id).all()
    decisions_made = 0
    
    for record in records:
        # Simulate decision based on risk indicators with some realistic variation
        escalate_probability = 0.1  # Base probability
        
        # Increase probability for suspicious patterns
        if 'exe' in record.attachments.lower() or 'scr' in record.attachments.lower():
            escalate_probability += 0.7
        if 'urgent' in record.subject.lower() or 'immediate' in record.subject.lower():
            escalate_probability += 0.4
        if record.leaver.lower() == 'yes':
            escalate_probability += 0.3
        if any(domain in record.sender.lower() for domain in ['suspicious', 'fake', 'phishing']):
            escalate_probability += 0.8
        if 'confidential' in record.subject.lower() or 'wire transfer' in record.subject.lower():
            escalate_probability += 0.5
        
        # Make decision with some randomness for realism
        if random.random() < escalate_probability:
            decision = 'Escalated'
            record.escalated_at = datetime.utcnow()
        else:
            decision = 'Cleared'
            record.resolved_at = datetime.utcnow()
        
        record.case_status = decision
        
        # Record feedback for ML learning
        feedback = MLFeedback(
            session_id=session_id,
            record_id=record.record_id,
            user_decision=decision,
            original_ml_score=record.ml_risk_score,
            decision_timestamp=datetime.utcnow()
        )
        db.session.add(feedback)
        decisions_made += 1
        
        # Learn progressively every 10 decisions
        if decisions_made % 10 == 0:
            print(f"  Learning from {decisions_made} decisions...")
            adaptive_engine.learn_from_user_decisions(session_id)
    
    db.session.commit()
    
    escalated = len([r for r in records if r.case_status == 'Escalated'])
    cleared = len([r for r in records if r.case_status == 'Cleared'])
    
    print(f"✓ Simulated {decisions_made} user decisions:")
    print(f"  - Escalated: {escalated} cases ({escalated/decisions_made*100:.1f}%)")
    print(f"  - Cleared: {cleared} cases ({cleared/decisions_made*100:.1f}%)")
    
    return decisions_made

def demonstrate_learning_evolution(session_id, adaptive_engine):
    """Show how the model evolves through learning"""
    print("\nDemonstrating adaptive learning evolution...")
    
    # Get initial analytics
    initial_analytics = adaptive_engine.get_learning_analytics(days=1)
    
    # Trigger final comprehensive learning
    print("Triggering comprehensive learning from all decisions...")
    success = adaptive_engine.learn_from_user_decisions(session_id)
    
    if success:
        print("✓ Adaptive learning completed successfully!")
        
        # Get updated analytics
        final_analytics = adaptive_engine.get_learning_analytics(days=1)
        
        print("\nLearning Results:")
        print(f"  - Model Maturity: {final_analytics['performance_metrics'].get('model_maturity', 'Unknown')}")
        print(f"  - Adaptive Weight: {final_analytics['performance_metrics'].get('adaptive_weight', 0)*100:.1f}%")
        print(f"  - Learning Confidence: {final_analytics['performance_metrics'].get('learning_confidence', 0)*100:.1f}%")
        print(f"  - Total Decisions Learned: {final_analytics['learning_trends'].get('total_decisions_learned', 0)}")
        
        # Show key insights
        insights = final_analytics.get('feature_insights', {})
        print(f"\nKey Learning Insights:")
        for indicator in insights.get('top_risk_indicators', []):
            print(f"  - {indicator}")
        
        print(f"\nLearned Patterns:")
        for pattern in insights.get('learned_patterns', []):
            print(f"  - {pattern}")
            
        return True
    else:
        print("✗ Learning failed - insufficient data or error occurred")
        return False

def run_new_data_analysis(session_id, adaptive_engine):
    """Demonstrate how the adaptive model performs on new data"""
    print("\nAnalyzing new data with trained adaptive model...")
    
    # Run adaptive analysis on the session
    analysis_results = adaptive_engine.analyze_session_with_learning(session_id)
    
    if analysis_results:
        stats = analysis_results.get('processing_stats', {})
        insights = analysis_results.get('insights', {})
        
        print("✓ Adaptive analysis completed!")
        print(f"  - Records Analyzed: {stats.get('ml_records_analyzed', 0)}")
        print(f"  - Anomalies Detected: {stats.get('anomalies_detected', 0)}")
        print(f"  - Critical Cases: {stats.get('critical_cases', 0)}")
        print(f"  - High Risk Cases: {stats.get('high_risk_cases', 0)}")
        print(f"  - Adaptive Weight Used: {stats.get('adaptive_weight_used', 0)*100:.1f}%")
        print(f"  - Learning Status: {insights.get('learning_status', 'Unknown')}")
        
        return True
    else:
        print("✗ Adaptive analysis failed")
        return False

def main():
    """Main demonstration function"""
    print("=" * 60)
    print("EMAIL GUARDIAN ADAPTIVE ML LEARNING DEMONSTRATION")
    print("=" * 60)
    
    with app.app_context():
        # Initialize adaptive ML engine
        adaptive_engine = AdaptiveMLEngine()
        
        # Step 1: Create demo session with sample data
        session_id = create_demo_session()
        
        # Step 2: Simulate user decisions
        decisions_made = simulate_user_decisions(session_id, adaptive_engine)
        
        # Step 3: Demonstrate learning evolution
        learning_success = demonstrate_learning_evolution(session_id, adaptive_engine)
        
        # Step 4: Show adaptive analysis on new data
        if learning_success:
            analysis_success = run_new_data_analysis(session_id, adaptive_engine)
        
        print("\n" + "=" * 60)
        print("DEMONSTRATION COMPLETE!")
        print("=" * 60)
        print(f"✓ Demo session created: {session_id}")
        print(f"✓ User decisions simulated: {decisions_made}")
        print(f"✓ Adaptive learning: {'Success' if learning_success else 'Failed'}")
        
        print(f"\nYou can now:")
        print(f"1. Visit the dashboard: /dashboard/{session_id}")
        print(f"2. View adaptive ML analytics: /adaptive_ml_dashboard/{session_id}")
        print(f"3. Review case decisions: /cases/{session_id}")
        print(f"4. Check escalations: /escalations/{session_id}")
        
        print(f"\nThe adaptive ML system will continue learning from your real decisions!")

if __name__ == "__main__":
    main()