
#!/usr/bin/env python3
"""
Set up default workflow data (rules and whitelist domains)
"""

from app import app, db
from models import Rule, WhitelistDomain

def setup_default_data():
    with app.app_context():
        print("=== Setting up default workflow data ===")
        
        # Create default exclusion rules
        exclusion_rules = [
            {
                'name': 'Test Exclusion Rule',
                'description': 'Exclude test emails',
                'conditions': {'field': 'subject', 'operator': 'contains', 'value': 'test'},
                'actions': {'exclude': True}
            }
        ]
        
        for rule_data in exclusion_rules:
            existing = Rule.query.filter_by(name=rule_data['name']).first()
            if not existing:
                rule = Rule(
                    name=rule_data['name'],
                    description=rule_data['description'],
                    rule_type='exclusion',
                    conditions=rule_data['conditions'],
                    actions=rule_data['actions'],
                    priority=1,
                    is_active=True
                )
                db.session.add(rule)
                print(f"Added exclusion rule: {rule_data['name']}")
        
        # Create default security rules
        security_rules = [
            {
                'name': 'High Risk External Domain',
                'description': 'Flag emails to external domains',
                'conditions': {'field': 'recipients_email_domain', 'operator': 'contains', 'value': 'gmail'},
                'actions': {'flag': True, 'risk_level': 'high'}
            }
        ]
        
        for rule_data in security_rules:
            existing = Rule.query.filter_by(name=rule_data['name']).first()
            if not existing:
                rule = Rule(
                    name=rule_data['name'],
                    description=rule_data['description'],
                    rule_type='security',
                    conditions=rule_data['conditions'],
                    actions=rule_data['actions'],
                    priority=50,
                    is_active=True
                )
                db.session.add(rule)
                print(f"Added security rule: {rule_data['name']}")
        
        # Create default whitelist domains
        whitelist_domains = [
            'company.com',
            'corp.com',
            'example.com'
        ]
        
        for domain in whitelist_domains:
            existing = WhitelistDomain.query.filter_by(domain=domain).first()
            if not existing:
                whitelist_entry = WhitelistDomain(
                    domain=domain,
                    domain_type='Corporate',
                    added_by='System'
                )
                db.session.add(whitelist_entry)
                print(f"Added whitelist domain: {domain}")
        
        db.session.commit()
        print("Setup completed!")

if __name__ == "__main__":
    setup_default_data()
