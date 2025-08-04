import numpy as np
import pandas as pd
import json
import logging
from datetime import datetime
from sklearn.ensemble import IsolationForest
from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
from models import EmailRecord, AttachmentKeyword
from performance_config import config
from app import db

logger = logging.getLogger(__name__)

class MLEngine:
    """Machine learning engine for anomaly detection and risk scoring"""

    def __init__(self):
        self.isolation_forest = None
        self.dbscan = None
        self.tfidf_vectorizer = TfidfVectorizer(max_features=config.tfidf_max_features, stop_words='english')
        self.scaler = StandardScaler()
        self.fast_mode = config.fast_mode
        # Cache attachment keywords to avoid repeated DB queries
        self._attachment_keywords_cache = None
        logger.info(f"MLEngine initialized with fast_mode={self.fast_mode}")

        # Risk thresholds
        self.risk_thresholds = {
            'critical': 0.8,
            'high': 0.6,
            'medium': 0.4,
            'low': 0.0
        }

    def analyze_session(self, session_id):
        """Perform comprehensive ML analysis on session data"""
        try:
            logger.info(f"Starting ML analysis for session {session_id}")

            # Get record counts in a single optimized query
            from sqlalchemy import func, case
            counts = db.session.query(
                func.count().label('total'),
                func.sum(case((EmailRecord.excluded_by_rule.isnot(None), 1), else_=0)).label('excluded'),
                func.sum(case((EmailRecord.whitelisted == True, 1), else_=0)).label('whitelisted')
            ).filter(EmailRecord.session_id == session_id).first()
            
            logger.info(f"Session stats - Total: {counts.total}, Excluded: {counts.excluded}, Whitelisted: {counts.whitelisted}")

            # Get records for ML analysis in batches (limit for performance)
            max_records = min(config.max_ml_records, 10000) if self.fast_mode else config.max_ml_records
            records = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.excluded_by_rule.is_(None),
                db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False),
                db.or_(EmailRecord.risk_level.is_(None), EmailRecord.risk_level == '')
            ).limit(max_records).all()
            
            logger.info(f"Processing {len(records)} records for ML analysis (limited to {max_records} for performance)")

            if len(records) < 5:  # Minimum for meaningful ML analysis
                logger.warning(f"Too few records ({len(records)}) for ML analysis - assigning default risk levels")
                
                # Still update records with basic risk assessment even if too few for ML
                # Batch update for better performance
                update_count = 0
                for record in records:
                    if record.ml_risk_score is None:
                        record.ml_risk_score = 0.1  # Low risk default
                        record.risk_level = 'Low'
                        record.ml_explanation = 'Low risk - insufficient data for ML analysis'
                        update_count += 1
                        
                        # Batch commit every batch_commit_size records
                        if update_count % config.batch_commit_size == 0:
                            db.session.commit()
                
                # Final commit for remaining records
                if update_count % config.batch_commit_size != 0:
                    db.session.commit()
                return {'processing_stats': {'ml_records_analyzed': len(records)}}

            # Fast mode: limit records for processing speed
            if self.fast_mode and len(records) > config.max_ml_records:
                logger.info(f"Fast mode: Processing sample of {config.max_ml_records} records out of {len(records)}")
                records = records[:config.max_ml_records]

            # Convert to DataFrame for analysis
            df = self._records_to_dataframe(records)

            # Feature engineering
            features = self._engineer_features(df)

            # Anomaly detection
            anomaly_scores = self._detect_anomalies(features)

            # Risk scoring
            risk_scores = self._calculate_risk_scores(df, anomaly_scores)

            # Update records with ML results
            self._update_records_with_ml_results(records, anomaly_scores, risk_scores)

            # Skip complex insights generation in fast mode for performance
            if self.fast_mode:
                insights = {'summary': f'ML analysis completed for {len(records)} records', 'fast_mode': True}
            else:
                insights = self._generate_insights(df, anomaly_scores, risk_scores)

            logger.info(f"ML analysis completed for session {session_id}")

            return {
                'processing_stats': {
                    'ml_records_analyzed': len(records),
                    'anomalies_detected': sum(1 for score in anomaly_scores if score > 0.5),
                    'critical_cases': sum(1 for score in risk_scores if score > self.risk_thresholds['critical']),
                    'high_risk_cases': sum(1 for score in risk_scores if score > self.risk_thresholds['high'])
                },
                'insights': insights
            }

        except Exception as e:
            logger.error(f"Error in ML analysis for session {session_id}: {str(e)}")
            
            # When ML fails, still assign basic risk scores to all records
            try:
                records = EmailRecord.query.filter(
                    EmailRecord.session_id == session_id,
                    EmailRecord.excluded_by_rule.is_(None),
                    db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
                ).all()
                
                logger.info(f"Applying basic risk scoring to {len(records)} records after ML failure")
                
                for record in records:
                    # Calculate basic risk score without ML
                    basic_risk = self._calculate_basic_risk_score(record)
                    record.ml_risk_score = basic_risk
                    record.risk_level = self._get_risk_level(basic_risk)
                    record.ml_explanation = f'Basic risk assessment (ML failed): {record.risk_level} risk'
                
                # Batch commit for performance
                db.session.commit()
                logger.info(f"Applied basic risk scores to {len(records)} records")
                
                return {
                    'processing_stats': {
                        'ml_records_analyzed': len(records),
                        'anomalies_detected': 0,
                        'critical_cases': sum(1 for r in records if r.ml_risk_score > self.risk_thresholds['critical']),
                        'high_risk_cases': sum(1 for r in records if r.ml_risk_score > self.risk_thresholds['high']),
                        'basic_scoring_used': True
                    },
                    'insights': {'info': f'Used basic risk scoring due to ML error: {str(e)}'}
                }
            except Exception as fallback_error:
                logger.error(f"Fallback basic scoring also failed: {str(fallback_error)}")
                return {
                    'processing_stats': {
                        'ml_records_analyzed': 0,
                        'anomalies_detected': 0,
                        'critical_cases': 0,
                        'high_risk_cases': 0,
                        'error': str(e)
                    },
                    'insights': {'error': f'ML analysis and fallback failed: {str(e)}'}
                }

    def _records_to_dataframe(self, records):
        """Convert EmailRecord objects to pandas DataFrame"""
        data = []
        for record in records:
            data.append({
                'record_id': record.record_id,
                'sender': record.sender or '',
                'subject': record.subject or '',
                'attachments': record.attachments or '',
                'recipients': record.recipients or '',
                'recipients_email_domain': record.recipients_email_domain or '',
                'wordlist_attachment': record.wordlist_attachment or '',
                'wordlist_subject': record.wordlist_subject or '',
                'justification': record.justification or '',
                'time': record.time or '',
                'leaver': record.leaver or '',
                'department': record.department or '',
                'bunit': record.bunit or ''
            })

        return pd.DataFrame(data)

    def _engineer_features(self, df):
        """Engineer features for ML analysis"""
        features = []

        for _, row in df.iterrows():
            feature_vector = []

            # Text-based features
            subject_len = len(row['subject'])
            has_attachments = 1 if row['attachments'] else 0
            has_wordlist_match = self._check_custom_wordlist_match(row['subject'], row['attachments'])

            # Domain features
            domain = row['recipients_email_domain'].lower()
            is_external = 1 if domain and not any(corp in domain for corp in ['company.com', 'corp.com']) else 0
            is_public_domain = 1 if any(pub in domain for pub in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']) else 0

            # Temporal features (if time parsing is possible)
            is_weekend = 0
            is_after_hours = 0
            try:
                # Basic time analysis - can be enhanced
                if 'weekend' in row['time'].lower():
                    is_weekend = 1
                if any(hour in row['time'] for hour in ['22:', '23:', '00:', '01:', '02:', '03:', '04:', '05:']):
                    is_after_hours = 1
            except:
                pass

            # Leaver status
            is_leaver = 1 if row['leaver'].lower() in ['yes', 'true', '1'] else 0

            # Attachment risk features
            attachment_risk = self._calculate_attachment_risk(row['attachments'])

            # Justification sentiment (basic)
            justification_len = len(row['justification'])
            has_justification = 1 if justification_len > 0 else 0

            feature_vector = [
                subject_len,
                has_attachments,
                has_wordlist_match,
                is_external,
                is_public_domain,
                is_weekend,
                is_after_hours,
                is_leaver,
                attachment_risk,
                justification_len,
                has_justification
            ]

            features.append(feature_vector)

        return np.array(features)

    def _calculate_attachment_risk(self, attachments):
        """Calculate risk score for attachments"""
        if not attachments:
            return 0.0

        attachments_lower = attachments.lower()
        risk_score = 0.0

        # High-risk extensions
        high_risk_extensions = ['.exe', '.scr', '.bat', '.cmd', '.com', '.pif', '.vbs', '.js']
        for ext in high_risk_extensions:
            if ext in attachments_lower:
                risk_score += 0.8

        # Medium-risk extensions
        medium_risk_extensions = ['.zip', '.rar', '.7z', '.doc', '.docx', '.xls', '.xlsx', '.pdf']
        for ext in medium_risk_extensions:
            if ext in attachments_lower:
                risk_score += 0.3

        # Suspicious patterns
        suspicious_patterns = ['double extension', 'hidden', 'confidential', 'urgent', 'invoice']
        for pattern in suspicious_patterns:
            if pattern in attachments_lower:
                risk_score += 0.2

        # Get attachment keywords from cache to avoid repeated DB queries
        if self._attachment_keywords_cache is None:
            try:
                keywords = AttachmentKeyword.query.filter_by(is_active=True).all()
                self._attachment_keywords_cache = keywords
            except:
                self._attachment_keywords_cache = []
                
        for keyword in self._attachment_keywords_cache:
            if keyword.keyword.lower() in attachments_lower:
                if keyword.category == 'Suspicious':
                    risk_score += keyword.risk_score * 0.1
                elif keyword.category == 'Personal':
                    risk_score += keyword.risk_score * 0.05

        return min(risk_score, 1.0)  # Cap at 1.0

    def _check_custom_wordlist_match(self, subject, attachments):
        """Check if subject or attachments match custom wordlist"""
        try:
            # Get risk keywords from cache
            if self._attachment_keywords_cache is None:
                keywords = AttachmentKeyword.query.filter_by(
                    is_active=True, 
                    keyword_type='risk'
                ).all()
                self._attachment_keywords_cache = keywords
            
            subject_lower = (subject or '').lower()
            attachments_lower = (attachments or '').lower()
            
            for keyword in self._attachment_keywords_cache:
                keyword_lower = keyword.keyword.lower()
                
                # Check based on applies_to setting
                if keyword.applies_to in ['subject', 'both'] and keyword_lower in subject_lower:
                    return 1
                if keyword.applies_to in ['attachment', 'both'] and keyword_lower in attachments_lower:
                    return 1
            
            return 0
        except Exception as e:
            logger.error(f"Error checking custom wordlist: {str(e)}")
            return 0

    def _calculate_wordlist_risk(self, subject, attachments):
        """Calculate risk score based on custom wordlist matches"""
        try:
            if self._attachment_keywords_cache is None:
                keywords = AttachmentKeyword.query.filter_by(
                    is_active=True, 
                    keyword_type='risk'
                ).all()
                self._attachment_keywords_cache = keywords
            
            subject_lower = (subject or '').lower()
            attachments_lower = (attachments or '').lower()
            total_risk = 0.0
            
            for keyword in self._attachment_keywords_cache:
                keyword_lower = keyword.keyword.lower()
                matched = False
                
                # Check based on applies_to setting
                if keyword.applies_to in ['subject', 'both'] and keyword_lower in subject_lower:
                    matched = True
                elif keyword.applies_to in ['attachment', 'both'] and keyword_lower in attachments_lower:
                    matched = True
                
                if matched:
                    # Scale risk score based on category
                    if keyword.category == 'Suspicious':
                        total_risk += keyword.risk_score * 0.05  # Higher impact
                    elif keyword.category == 'Personal':
                        total_risk += keyword.risk_score * 0.03
                    else:  # Business
                        total_risk += keyword.risk_score * 0.01
            
            return min(total_risk, 0.3)  # Cap wordlist contribution at 0.3
        except Exception as e:
            logger.error(f"Error calculating wordlist risk: {str(e)}")
            return 0.0

    def _detect_anomalies(self, features):
        """Detect anomalies using Isolation Forest"""
        try:
            if len(features) < 10:
                # Too few samples for meaningful anomaly detection
                logger.info("Too few samples for anomaly detection, using basic scoring")
                return np.zeros(len(features))

            # Normalize features
            features_scaled = self.scaler.fit_transform(features)

            # Train Isolation Forest with minimal configuration for threading safety
            self.isolation_forest = IsolationForest(
                contamination=0.1,  # Use fixed contamination rate instead of 'auto'
                random_state=42,
                n_estimators=min(50, config.ml_estimators),  # Limit estimators for speed
                n_jobs=1,  # Single thread only
                bootstrap=False,  # Disable bootstrap for consistency
                verbose=0  # Disable verbose output
            )

            # Fit and predict with error handling
            try:
                anomaly_labels = self.isolation_forest.fit_predict(features_scaled)
                anomaly_scores = self.isolation_forest.decision_function(features_scaled)
                
                # Convert to 0-1 scale (higher = more anomalous)
                if len(set(anomaly_scores)) > 1:  # Check if we have variation
                    anomaly_scores_normalized = np.interp(anomaly_scores, 
                                                        (anomaly_scores.min(), anomaly_scores.max()), 
                                                        (0, 1))
                    # Invert so higher scores mean more anomalous
                    anomaly_scores_normalized = 1 - anomaly_scores_normalized
                else:
                    # All scores are the same, return zeros
                    anomaly_scores_normalized = np.zeros(len(features))
                
                logger.info(f"Anomaly detection completed successfully for {len(features)} records")
                return anomaly_scores_normalized
                
            except Exception as fit_error:
                logger.error(f"Error during IsolationForest fit/predict: {str(fit_error)}")
                # Fallback to simple rule-based anomaly scoring
                return self._simple_anomaly_scoring(features)

        except Exception as e:
            logger.error(f"Error in anomaly detection setup: {str(e)}")
            return self._simple_anomaly_scoring(features)

    def _calculate_risk_scores(self, df, anomaly_scores):
        """Calculate comprehensive risk scores"""
        risk_scores = []

        for i, (_, row) in enumerate(df.iterrows()):
            base_risk = 0.0

            # Anomaly contribution (40% of score)
            anomaly_contribution = anomaly_scores[i] * 0.4

            # Rule-based risk factors (60% of score)
            rule_risk = 0.0

            # High-risk indicators
            if row['leaver'].lower() in ['yes', 'true', '1']:
                rule_risk += 0.3

            # External domain risk
            domain = row['recipients_email_domain'].lower()
            if any(pub in domain for pub in ['gmail.com', 'yahoo.com', 'hotmail.com']):
                rule_risk += 0.2

            # Attachment risk
            attachment_risk = self._calculate_attachment_risk(row['attachments'])
            rule_risk += attachment_risk * 0.3

            # Custom wordlist matches
            wordlist_risk = self._calculate_wordlist_risk(row['subject'], row['attachments'])
            rule_risk += wordlist_risk

            # Time-based risk (basic implementation)
            if 'weekend' in row['time'].lower():
                rule_risk += 0.1

            # Justification analysis (basic sentiment)
            justification = row['justification'].lower()
            suspicious_justification_terms = ['urgent', 'confidential', 'personal', 'mistake', 'wrong']
            if any(term in justification for term in suspicious_justification_terms):
                rule_risk += 0.1

            # Combine scores
            total_risk = anomaly_contribution + (rule_risk * 0.6)
            risk_scores.append(min(total_risk, 1.0))  # Cap at 1.0

        return risk_scores

    def _update_records_with_ml_results(self, records, anomaly_scores, risk_scores):
        """Update database records with ML results using batch processing"""
        try:
            logger.info(f"Updating {len(records)} records with ML results using batch processing")
            batch_count = 0
            
            for i, record in enumerate(records):
                record.ml_anomaly_score = float(anomaly_scores[i])
                record.ml_risk_score = float(risk_scores[i])

                # Assign risk level efficiently
                risk_score = risk_scores[i]
                if risk_score >= 0.8:
                    record.risk_level = 'Critical'
                elif risk_score >= 0.6:
                    record.risk_level = 'High'
                elif risk_score >= 0.4:
                    record.risk_level = 'Medium'
                else:
                    record.risk_level = 'Low'

                # Generate simplified explanation for performance
                if risk_score >= 0.6:
                    record.ml_explanation = f'{record.risk_level} risk (anomaly: {anomaly_scores[i]:.2f}, risk: {risk_score:.2f})'
                else:
                    record.ml_explanation = f'{record.risk_level} risk'
                
                batch_count += 1
                
                # Batch commit every 500 records for performance
                if batch_count % 500 == 0:
                    db.session.commit()
                    logger.info(f"Committed batch {batch_count // 500}: {batch_count} records updated")

            # Final commit for remaining records
            if batch_count % 500 != 0:
                db.session.commit()
            
            logger.info(f"ML database updates completed: {len(records)} records updated in {(batch_count // 500) + 1} batches")

        except Exception as e:
            logger.error(f"Error updating records with ML results: {str(e)}")
            db.session.rollback()
            raise

    def _generate_explanation(self, record, anomaly_score, risk_score):
        """Generate human-readable explanation for ML scoring"""
        explanations = []

        if anomaly_score > 0.7:
            explanations.append("Unusual communication pattern detected")

        if record.leaver and record.leaver.lower() in ['yes', 'true', '1']:
            explanations.append("Sender is a leaver - high risk for data exfiltration")

        domain = (record.recipients_email_domain or '').lower()
        if any(pub in domain for pub in ['gmail.com', 'yahoo.com', 'hotmail.com']):
            explanations.append("Email sent to public domain")

        if record.attachments:
            attachment_risk = self._calculate_attachment_risk(record.attachments)
            if attachment_risk > 0.5:
                explanations.append("High-risk attachments detected")

        if record.wordlist_attachment or record.wordlist_subject:
            explanations.append("Sensitive keywords detected")

        if not explanations:
            explanations.append("Low risk communication")

        return "; ".join(explanations)

    def _generate_insights(self, df, anomaly_scores, risk_scores):
        """Generate session-level insights"""
        insights = {
            'total_analyzed': len(df),
            'anomaly_rate': float(np.mean(anomaly_scores > 0.5)),
            'average_risk_score': float(np.mean(risk_scores)),
            'risk_distribution': {
                'critical': int(sum(1 for score in risk_scores if score > self.risk_thresholds['critical'])),
                'high': int(sum(1 for score in risk_scores if score > self.risk_thresholds['high'] and score <= self.risk_thresholds['critical'])),
                'medium': int(sum(1 for score in risk_scores if score > self.risk_thresholds['medium'] and score <= self.risk_thresholds['high'])),
                'low': int(sum(1 for score in risk_scores if score <= self.risk_thresholds['medium']))
            },
            'top_risk_factors': self._identify_top_risk_factors(df, risk_scores),
            'recommendations': self._generate_recommendations(df, risk_scores)
        }

        return insights

    def _identify_top_risk_factors(self, df, risk_scores):
        """Identify top contributing risk factors"""
        risk_factors = []

        # Analyze high-risk cases
        high_risk_indices = [i for i, score in enumerate(risk_scores) if score > 0.6]

        if high_risk_indices:
            high_risk_df = df.iloc[high_risk_indices]

            # Check common patterns
            leaver_rate = (high_risk_df['leaver'].str.lower().isin(['yes', 'true', '1'])).mean()
            external_rate = high_risk_df['recipients_email_domain'].str.contains('gmail|yahoo|hotmail', na=False).mean()
            attachment_rate = (high_risk_df['attachments'] != '').mean()

            if leaver_rate > 0.3:
                risk_factors.append(f"Leaver communications ({leaver_rate:.1%} of high-risk cases)")
            if external_rate > 0.3:
                risk_factors.append(f"External domain communications ({external_rate:.1%} of high-risk cases)")
            if attachment_rate > 0.3:
                risk_factors.append(f"Communications with attachments ({attachment_rate:.1%} of high-risk cases)")

        return risk_factors

    def _generate_recommendations(self, df, risk_scores):
        """Generate actionable recommendations"""
        recommendations = []

        critical_count = sum(1 for score in risk_scores if score > self.risk_thresholds['critical'])
        if critical_count > 0:
            recommendations.append(f"Immediately review {critical_count} critical risk cases")

        high_count = sum(1 for score in risk_scores if score > self.risk_thresholds['high'])
        if high_count > 5:
            recommendations.append(f"Schedule review of {high_count} high-risk cases within 24 hours")

        # Domain-specific recommendations
        external_domains = df[df['recipients_email_domain'].str.contains('gmail|yahoo|hotmail', na=False)]
        if len(external_domains) > len(df) * 0.2:
            recommendations.append("Consider updating domain whitelist policies - high volume of external communications")

        return recommendations

    def get_insights(self, session_id):
        """Get ML insights for dashboard display"""
        try:
            session_records = EmailRecord.query.filter_by(session_id=session_id).all()

            if not session_records:
                return {
                    'total_records': 0,
                    'analyzed_records': 0,
                    'risk_distribution': {'Critical': 0, 'High': 0, 'Medium': 0, 'Low': 0},
                    'average_risk_score': 0.0,
                    'processing_complete': False,
                    'error': 'No records found for session'
                }

            # Calculate statistics
            total_records = len(session_records)
            analyzed_records = len([r for r in session_records if r.ml_risk_score is not None])

            # Initialize risk distribution with default values
            risk_distribution = {'Critical': 0, 'High': 0, 'Medium': 0, 'Low': 0}
            avg_risk_score = 0.0

            if analyzed_records > 0:
                risk_levels = [r.risk_level for r in session_records if r.risk_level]
                for level in ['Critical', 'High', 'Medium', 'Low']:
                    risk_distribution[level] = risk_levels.count(level)

                risk_scores = [r.ml_risk_score for r in session_records if r.ml_risk_score is not None]
                avg_risk_score = float(np.mean(risk_scores)) if risk_scores else 0.0

            insights = {
                'total_records': total_records,
                'analyzed_records': analyzed_records,
                'risk_distribution': risk_distribution,
                'average_risk_score': avg_risk_score,
                'processing_complete': analyzed_records > 0
            }

            return insights

        except Exception as e:
            logger.error(f"Error getting insights for session {session_id}: {str(e)}")
            return {
                'total_records': 0,
                'analyzed_records': 0,
                'risk_distribution': {'Critical': 0, 'High': 0, 'Medium': 0, 'Low': 0},
                'average_risk_score': 0.0,
                'processing_complete': False,
                'error': str(e)
            }
    
    def _calculate_basic_risk_score(self, record):
        """Calculate basic risk score without ML analysis"""
        risk_score = 0.0
        
        # Leaver status (30% of risk)
        if record.leaver and record.leaver.lower() in ['yes', 'true', '1']:
            risk_score += 0.3
        
        # External domain (20% of risk)
        if record.recipients_email_domain:
            domain = record.recipients_email_domain.lower()
            if any(pub in domain for pub in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']):
                risk_score += 0.2
        
        # Attachment risk (25% of risk)
        if record.attachments:
            attachment_risk = self._calculate_attachment_risk(record.attachments)
            risk_score += attachment_risk * 0.25
        
        # Wordlist matches (15% of risk)
        if record.wordlist_attachment or record.wordlist_subject:
            risk_score += 0.15
        
        # Subject length (10% of risk) - very long or very short subjects can be suspicious
        if record.subject:
            subject_len = len(record.subject)
            if subject_len < 5 or subject_len > 100:
                risk_score += 0.1
        
        return min(risk_score, 1.0)  # Cap at 1.0
    
    def _simple_anomaly_scoring(self, features):
        """Simple rule-based anomaly scoring as fallback"""
        try:
            logger.info("Using simple anomaly scoring fallback")
            anomaly_scores = []
            
            for feature_vector in features:
                # Simple scoring based on feature values
                # feature_vector indices: [subject_len, has_attachments, has_wordlist_match, 
                #                         is_external, is_public_domain, is_weekend, 
                #                         is_after_hours, is_leaver, attachment_risk, 
                #                         justification_len, has_justification]
                
                score = 0.0
                
                # High risk indicators
                if len(feature_vector) > 7 and feature_vector[7] > 0:  # is_leaver
                    score += 0.4
                if len(feature_vector) > 4 and feature_vector[4] > 0:  # is_public_domain
                    score += 0.3
                if len(feature_vector) > 8 and feature_vector[8] > 0.5:  # attachment_risk
                    score += 0.3
                if len(feature_vector) > 2 and feature_vector[2] > 0:  # has_wordlist_match
                    score += 0.2
                if len(feature_vector) > 6 and feature_vector[6] > 0:  # is_after_hours
                    score += 0.1
                
                # Cap the score at 1.0
                anomaly_scores.append(min(score, 1.0))
            
            return np.array(anomaly_scores)
            
        except Exception as e:
            logger.error(f"Error in simple anomaly scoring: {str(e)}")
            return np.zeros(len(features))

    def _get_risk_level(self, risk_score):
        """Convert numeric risk score to risk level string"""
        if risk_score >= self.risk_thresholds['critical']:
            return 'Critical'
        elif risk_score >= self.risk_thresholds['high']:
            return 'High'
        elif risk_score >= self.risk_thresholds['medium']:
            return 'Medium'
        else:
            return 'Low'