
#!/usr/bin/env python3
"""
Debug script to check workflow components
"""

from app import app, db
from models import Rule, WhitelistDomain, EmailRecord, ProcessingSession

def check_workflow_components():
    with app.app_context():
        print("=== Email Guardian Workflow Debug ===")
        
        # Check rules
        exclusion_rules = Rule.query.filter_by(rule_type='exclusion', is_active=True).all()
        security_rules = Rule.query.filter_by(rule_type='security', is_active=True).all()
        
        print(f"\nActive Exclusion Rules: {len(exclusion_rules)}")
        for rule in exclusion_rules:
            print(f"  - {rule.name}: {rule.conditions}")
            
        print(f"\nActive Security Rules: {len(security_rules)}")
        for rule in security_rules:
            print(f"  - {rule.name}: {rule.conditions}")
        
        # Check whitelist domains
        whitelist_domains = WhitelistDomain.query.filter_by(is_active=True).all()
        print(f"\nActive Whitelist Domains: {len(whitelist_domains)}")
        for domain in whitelist_domains:
            print(f"  - {domain.domain}")
        
        # Check latest session
        latest_session = ProcessingSession.query.order_by(ProcessingSession.upload_time.desc()).first()
        if latest_session:
            print(f"\nLatest Session: {latest_session.id}")
            print(f"  Status: {latest_session.status}")
            print(f"  Total Records: {latest_session.total_records}")
            print(f"  Processed Records: {latest_session.processed_records}")
            print(f"  Exclusion Applied: {latest_session.exclusion_applied}")
            print(f"  Whitelist Applied: {latest_session.whitelist_applied}")
            print(f"  Rules Applied: {latest_session.rules_applied}")
            print(f"  ML Applied: {latest_session.ml_applied}")
            
            # Check some sample records
            sample_records = EmailRecord.query.filter_by(session_id=latest_session.id).limit(5).all()
            print(f"\nSample Records from Session:")
            for record in sample_records:
                print(f"  - {record.record_id}: {record.sender} -> {record.recipients_email_domain}")
                print(f"    Excluded: {record.excluded_by_rule}")
                print(f"    Whitelisted: {record.whitelisted}")
                print(f"    Risk Level: {record.risk_level}")
                print(f"    Rule Matches: {record.rule_matches}")

if __name__ == "__main__":
    check_workflow_components()
