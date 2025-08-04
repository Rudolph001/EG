
#!/usr/bin/env python3
"""
Setup script to populate Email Guardian with basic configuration
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Rule, WhitelistDomain, AttachmentKeyword

def setup_basic_rules():
    """Create basic security and exclusion rules"""
    with app.app_context():
        print("Setting up basic rules...")
        
        # Create exclusion rules
        exclusion_rules = [
            {
                'name': 'Exclude Test Emails',
                'rule_type': 'exclusion',
                'description': 'Exclude emails with test subjects',
                'conditions': {
                    'operator': 'OR',
                    'conditions': [
                        {'field': 'subject', 'operator': 'contains', 'value': 'test'},
                        {'field': 'subject', 'operator': 'contains', 'value': 'TEST'}
                    ]
                },
                'actions': {'exclude': True},
                'priority': 1
            }
        ]
        
        # Create security rules
        security_rules = [
            {
                'name': 'High Risk Leaver Communications',
                'rule_type': 'security',
                'description': 'Flag communications from employees who are leaving',
                'conditions': {
                    'operator': 'AND',
                    'conditions': [
                        {'field': 'leaver', 'operator': 'equals', 'value': 'yes'},
                        {'field': 'recipients_email_domain', 'operator': 'contains', 'value': 'gmail'}
                    ]
                },
                'actions': {'flag': True, 'risk_score': 0.8},
                'priority': 10
            },
            {
                'name': 'Suspicious Attachments',
                'rule_type': 'security',
                'description': 'Flag emails with high-risk attachment types',
                'conditions': {
                    'operator': 'OR',
                    'conditions': [
                        {'field': 'attachments', 'operator': 'contains', 'value': '.exe'},
                        {'field': 'attachments', 'operator': 'contains', 'value': '.zip'},
                        {'field': 'attachments', 'operator': 'contains', 'value': '.rar'}
                    ]
                },
                'actions': {'flag': True, 'risk_score': 0.6},
                'priority': 8
            },
            {
                'name': 'External Domain Communications',
                'rule_type': 'security',
                'description': 'Flag communications to public email domains',
                'conditions': {
                    'operator': 'OR',
                    'conditions': [
                        {'field': 'recipients_email_domain', 'operator': 'contains', 'value': 'gmail.com'},
                        {'field': 'recipients_email_domain', 'operator': 'contains', 'value': 'yahoo.com'},
                        {'field': 'recipients_email_domain', 'operator': 'contains', 'value': 'hotmail.com'}
                    ]
                },
                'actions': {'flag': True, 'risk_score': 0.4},
                'priority': 5
            }
        ]
        
        # Add all rules
        all_rules = exclusion_rules + security_rules
        rules_added = 0
        
        for rule_data in all_rules:
            # Check if rule already exists
            existing = Rule.query.filter_by(name=rule_data['name']).first()
            if not existing:
                rule = Rule(**rule_data)
                db.session.add(rule)
                rules_added += 1
                print(f"Added rule: {rule_data['name']}")
        
        db.session.commit()
        print(f"✅ Added {rules_added} rules")

def setup_whitelist_domains():
    """Create basic whitelist domains"""
    with app.app_context():
        print("Setting up whitelist domains...")
        
        whitelist_domains = [
            {'domain': 'company.com', 'domain_type': 'Corporate', 'notes': 'Main company domain'},
            {'domain': 'corp.com', 'domain_type': 'Corporate', 'notes': 'Corporate domain'},
            {'domain': 'internal.com', 'domain_type': 'Corporate', 'notes': 'Internal communications'},
            {'domain': 'trusted-partner.com', 'domain_type': 'Partner', 'notes': 'Trusted business partner'}
        ]
        
        domains_added = 0
        for domain_data in whitelist_domains:
            existing = WhitelistDomain.query.filter_by(domain=domain_data['domain']).first()
            if not existing:
                domain = WhitelistDomain(**domain_data)
                db.session.add(domain)
                domains_added += 1
                print(f"Added whitelist domain: {domain_data['domain']}")
        
        db.session.commit()
        print(f"✅ Added {domains_added} whitelist domains")

def setup_ml_keywords():
    """Create basic ML keywords and exclusion keywords"""
    with app.app_context():
        print("Setting up ML keywords...")
        
        # Risk assessment keywords
        risk_keywords = [
            # High-risk suspicious keywords
            {'keyword': 'urgent', 'category': 'Suspicious', 'risk_score': 8, 'keyword_type': 'risk', 'applies_to': 'both'},
            {'keyword': 'confidential', 'category': 'Suspicious', 'risk_score': 7, 'keyword_type': 'risk', 'applies_to': 'both'},
            {'keyword': 'personal use', 'category': 'Suspicious', 'risk_score': 9, 'keyword_type': 'risk', 'applies_to': 'both'},
            {'keyword': 'backup', 'category': 'Suspicious', 'risk_score': 6, 'keyword_type': 'risk', 'applies_to': 'attachment'},
            {'keyword': 'invoice', 'category': 'Suspicious', 'risk_score': 7, 'keyword_type': 'risk', 'applies_to': 'both'},
            {'keyword': 'payment', 'category': 'Suspicious', 'risk_score': 8, 'keyword_type': 'risk', 'applies_to': 'subject'},
            {'keyword': 'wire transfer', 'category': 'Suspicious', 'risk_score': 9, 'keyword_type': 'risk', 'applies_to': 'both'},
            {'keyword': 'resignation', 'category': 'Suspicious', 'risk_score': 8, 'keyword_type': 'risk', 'applies_to': 'subject'},
            
            # Business keywords
            {'keyword': 'meeting', 'category': 'Business', 'risk_score': 2, 'keyword_type': 'risk', 'applies_to': 'subject'},
            {'keyword': 'project', 'category': 'Business', 'risk_score': 2, 'keyword_type': 'risk', 'applies_to': 'both'},
            {'keyword': 'report', 'category': 'Business', 'risk_score': 2, 'keyword_type': 'risk', 'applies_to': 'both'},
            {'keyword': 'contract', 'category': 'Business', 'risk_score': 3, 'keyword_type': 'risk', 'applies_to': 'attachment'},
            
            # Personal keywords
            {'keyword': 'birthday', 'category': 'Personal', 'risk_score': 1, 'keyword_type': 'risk', 'applies_to': 'subject'},
            {'keyword': 'vacation', 'category': 'Personal', 'risk_score': 2, 'keyword_type': 'risk', 'applies_to': 'subject'},
            {'keyword': 'family', 'category': 'Personal', 'risk_score': 3, 'keyword_type': 'risk', 'applies_to': 'both'}
        ]
        
        # Exclusion keywords
        exclusion_keywords = [
            {'keyword': 'test', 'category': 'Exclusion', 'risk_score': 10, 'keyword_type': 'exclusion', 'applies_to': 'both'},
            {'keyword': 'demo', 'category': 'Exclusion', 'risk_score': 10, 'keyword_type': 'exclusion', 'applies_to': 'both'},
            {'keyword': 'sample', 'category': 'Exclusion', 'risk_score': 10, 'keyword_type': 'exclusion', 'applies_to': 'both'},
            {'keyword': 'training', 'category': 'Exclusion', 'risk_score': 10, 'keyword_type': 'exclusion', 'applies_to': 'subject'},
            {'keyword': 'example', 'category': 'Exclusion', 'risk_score': 10, 'keyword_type': 'exclusion', 'applies_to': 'both'}
        ]
        
        all_keywords = risk_keywords + exclusion_keywords
        keywords_added = 0
        
        for keyword_data in all_keywords:
            existing = AttachmentKeyword.query.filter_by(
                keyword=keyword_data['keyword'],
                keyword_type=keyword_data['keyword_type'],
                applies_to=keyword_data['applies_to']
            ).first()
            if not existing:
                keyword = AttachmentKeyword(**keyword_data)
                db.session.add(keyword)
                keywords_added += 1
                print(f"Added {keyword_data['keyword_type']} keyword: {keyword_data['keyword']} ({keyword_data['category']}, applies to: {keyword_data['applies_to']})")
        
        db.session.commit()
        print(f"✅ Added {keywords_added} keywords ({len(risk_keywords)} risk keywords, {len(exclusion_keywords)} exclusion keywords)")

def main():
    """Run complete setup"""
    print("🚀 Setting up Email Guardian basic configuration...")
    print("=" * 50)
    
    setup_basic_rules()
    print()
    setup_whitelist_domains()
    print()
    setup_ml_keywords()
    
    print("=" * 50)
    print("✅ Basic configuration setup complete!")
    print()
    print("Now you can:")
    print("1. Upload a new CSV file")
    print("2. Or reprocess an existing session to see the workflow in action")
    print()
    print("The workflow should now show:")
    print("- Exclusion rules filtering test emails")
    print("- Whitelist filtering for corporate domains")
    print("- Security rules flagging high-risk communications")
    print("- ML analysis with keyword matching")

if __name__ == '__main__':
    main()
