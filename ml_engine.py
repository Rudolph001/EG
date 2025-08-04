import numpy as np
import pandas as pd
import json
import logging
import signal
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
        def timeout_handler(signum, frame):
            raise TimeoutError("ML analysis timed out")
            
        try:
            # Set timeout for ML analysis (5 minutes max)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(300)  # 5 minute timeout
            
            logger.info(f"Starting ML analysis for session {session_id}")

            # Get all records first for debugging
            all_records = EmailRecord.query.filter_by(session_id=session_id).all()
            logger.info(f"Total records in session: {len(all_records)}")
            
            excluded_records = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.excluded_by_rule.isnot(None)
            ).all()
            logger.info(f"Excluded records: {len(excluded_records)}")
            
            whitelisted_records = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.whitelisted == True
            ).all()
            logger.info(f"Whitelisted records: {len(whitelisted_records)}")

            # Get non-excluded, non-whitelisted records
            records = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.excluded_by_rule.is_(None),
                db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
            ).all()
            
            logger.info(f"Records eligible for ML analysis: {len(records)}")

            if len(records) < 3:  # Reduced minimum for faster processing
                logger.warning(f"Too few records ({len(records)}) for ML analysis - updating existing records with default risk levels")
                
                # Still update records with basic risk assessment even if too few for ML
                for record in records:
                    if record.ml_risk_score is None:
                        record.ml_risk_score = 0.1  # Low risk default
                        record.risk_level = 'Low'
                        record.ml_explanation = 'Low risk - insufficient data for ML analysis'
                
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

            # Generate analysis insights
            insights = self._generate_insights(df, anomaly_scores, risk_scores)

            logger.info(f"ML analysis completed for session {session_id}")
            
            # Clear timeout
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)

            return {
                'processing_stats': {
                    'ml_records_analyzed': len(records),
                    'anomalies_detected': sum(1 for score in anomaly_scores if score > 0.5),
                    'critical_cases': sum(1 for score in risk_scores if score > self.risk_thresholds['critical']),
                    'high_risk_cases': sum(1 for score in risk_scores if score > self.risk_thresholds['high'])
                },
                'insights': insights
            }

        except TimeoutError as e:
            logger.error(f"ML analysis timed out for session {session_id}")
            # Clear timeout
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)
            # Return basic analysis with timeout info
            return {
                'processing_stats': {
                    'ml_records_analyzed': 0,
                    'anomalies_detected': 0,
                    'critical_cases': 0,
                    'high_risk_cases': 0,
                    'timeout': True
                },
                'insights': {'timeout': 'ML analysis timed out - using basic risk assessment'}
            }
        except Exception as e:
            logger.error(f"Error in ML analysis for session {session_id}: {str(e)}")
            # Clear timeout
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)
            # Return basic analysis instead of raising
            return {
                'processing_stats': {
                    'ml_records_analyzed': 0,
                    'anomalies_detected': 0,
                    'critical_cases': 0,
                    'high_risk_cases': 0,
                    'error': str(e)
                },
                'insights': {'error': f'ML analysis failed: {str(e)}'}
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
            has_wordlist_match = 1 if (row['wordlist_attachment'] or row['wordlist_subject']) else 0

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

    def _detect_anomalies(self, features):
        """Detect anomalies using Isolation Forest"""
        try:
            if len(features) < 10:
                # Too few samples for meaningful anomaly detection
                return np.zeros(len(features))

            # Normalize features
            features_scaled = self.scaler.fit_transform(features)

            # Train Isolation Forest (optimized for speed)
            self.isolation_forest = IsolationForest(
                contamination='auto',  # Use 'auto' instead of float for stability
                random_state=42,
                n_estimators=config.ml_estimators,
                n_jobs=1  # Always use single core for stability in Replit
            )

            # Fit and predict
            anomaly_labels = self.isolation_forest.fit_predict(features_scaled)
            anomaly_scores = self.isolation_forest.decision_function(features_scaled)

            # Convert to 0-1 scale (higher = more anomalous)
            anomaly_scores_normalized = np.interp(anomaly_scores, 
                                                (anomaly_scores.min(), anomaly_scores.max()), 
                                                (0, 1))

            # Invert so higher scores mean more anomalous
            anomaly_scores_normalized = 1 - anomaly_scores_normalized

            return anomaly_scores_normalized

        except Exception as e:
            logger.error(f"Error in anomaly detection: {str(e)}")
            return np.zeros(len(features))

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

            # Wordlist matches
            if row['wordlist_attachment'] or row['wordlist_subject']:
                rule_risk += 0.2

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
        """Update database records with ML results"""
        try:
            for i, record in enumerate(records):
                record.ml_anomaly_score = float(anomaly_scores[i])
                record.ml_risk_score = float(risk_scores[i])

                # Assign risk level
                risk_score = risk_scores[i]
                if risk_score >= self.risk_thresholds['critical']:
                    record.risk_level = 'Critical'
                elif risk_score >= self.risk_thresholds['high']:
                    record.risk_level = 'High'
                elif risk_score >= self.risk_thresholds['medium']:
                    record.risk_level = 'Medium'
                else:
                    record.risk_level = 'Low'

                # Generate explanation
                record.ml_explanation = self._generate_explanation(records[i], anomaly_scores[i], risk_scores[i])

            db.session.commit()
            logger.info(f"Updated {len(records)} records with ML results")

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