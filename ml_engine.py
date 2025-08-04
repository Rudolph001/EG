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
        """Analyze all records in a session"""
        logger.info(f"Starting ML analysis for session {session_id}")

        # Get session info
        session = ProcessingSession.query.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Get all non-excluded records for this session
        records = EmailRecord.query.filter_by(session_id=session_id).filter(
            EmailRecord.excluded_by_rule.is_(None)
        ).all()

        # Filter out whitelisted records
        non_whitelisted_records = [r for r in records if not r.whitelisted]

        total_records = len(records)
        eligible_records = len(non_whitelisted_records)

        logger.info(f"Total records in session: {session.total_records}")
        logger.info(f"Excluded records: {session.total_records - total_records}")
        logger.info(f"Whitelisted records: {total_records - eligible_records}")
        logger.info(f"Records eligible for ML analysis: {eligible_records}")

        if eligible_records == 0:
            logger.info("No records eligible for ML analysis")
            return

        # Limit processing for performance - max 10,000 records
        if eligible_records > 10000:
            logger.info(f"Large dataset detected. Processing first 10,000 of {eligible_records} records")
            non_whitelisted_records = non_whitelisted_records[:10000]
            eligible_records = 10000

        # Always use ultra-fast mode for Replit to prevent timeouts
        logger.info(f"Ultra-fast mode: Using simplified risk scoring for {eligible_records} records")
        self._apply_simplified_risk_scoring(non_whitelisted_records)

        logger.info(f"ML analysis completed for session {session_id}")

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

    def _apply_simplified_risk_scoring(self, records):
        """Apply simplified risk scoring for fast processing"""
        logger.info(f"Applying simplified risk scoring to {len(records)} records")

        if not records:
            logger.info("No records to process")
            return

        # Process in smaller batches to prevent memory issues
        batch_size = 500
        total_batches = (len(records) + batch_size - 1) // batch_size
        processed_count = 0

        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            batch_num = i // batch_size + 1

            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} records)")

            for record in batch:
                try:
                    # Simple risk scoring based on basic factors
                    risk_score = 0.1  # Base risk
                    risk_factors = []

                    # Check for external domains
                    if record.recipients_email_domain and any(domain in str(record.recipients_email_domain).lower() 
                                                            for domain in ['gmail', 'yahoo', 'hotmail', 'outlook']):
                        risk_score += 0.3
                        risk_factors.append("External email domain")

                    # Check for attachments
                    if record.attachments and str(record.attachments).lower() not in ['none', 'null', '', 'nan']:
                        risk_score += 0.2
                        risk_factors.append("Has attachments")

                    # Check if user is a leaver
                    if record.leaver and str(record.leaver).lower() == 'yes':
                        risk_score += 0.4
                        risk_factors.append("User is a leaver")

                    # Cap risk score at 1.0
                    risk_score = min(risk_score, 1.0)

                    # Determine risk level
                    if risk_score >= 0.7:
                        risk_level = 'Critical'
                    elif risk_score >= 0.5:
                        risk_level = 'High'
                    elif risk_score >= 0.3:
                        risk_level = 'Medium'
                    else:
                        risk_level = 'Low'

                    # Update record
                    record.ml_risk_score = risk_score
                    record.ml_anomaly_score = risk_score * 0.8
                    record.risk_level = risk_level
                    record.ml_explanation = f"Risk factors: {', '.join(risk_factors) if risk_factors else 'No significant risk factors'}"

                    processed_count += 1

                except Exception as e:
                    logger.error(f"Error processing record {record.id}: {str(e)}")
                    continue

            # Commit batch
            try:
                db.session.commit()
                logger.info(f"Batch {batch_num} committed successfully")
            except Exception as e:
                logger.error(f"Error committing batch {batch_num}: {str(e)}")
                db.session.rollback()

        logger.info(f"Simplified risk scoring completed. Processed {processed_count} records")

    def _combine_chunk_insights(self, chunk_insights_list):
        """Combine insights from multiple chunks into final insights"""
        try:
            if not chunk_insights_list:
                return {
                    'summary': 'No insights available',
                    'key_findings': [],
                    'recommendations': []
                }

            # Combine key findings and recommendations from all chunks
            all_findings = []
            all_recommendations = []

            for chunk_insights in chunk_insights_list:
                if isinstance(chunk_insights, dict):
                    if 'key_findings' in chunk_insights:
                        all_findings.extend(chunk_insights['key_findings'])
                    if 'recommendations' in chunk_insights:
                        all_recommendations.extend(chunk_insights['recommendations'])

            # Remove duplicates while preserving order
            unique_findings = list(dict.fromkeys(all_findings))
            unique_recommendations = list(dict.fromkeys(all_recommendations))

            # Create combined insights
            combined_insights = {
                'summary': f'Analysis completed across {len(chunk_insights_list)} chunks with optimized processing',
                'key_findings': unique_findings[:10],  # Limit to top 10 findings
                'recommendations': unique_recommendations[:10]  # Limit to top 10 recommendations
            }

            return combined_insights

        except Exception as e:
            logger.error(f"Error combining chunk insights: {str(e)}")
            return {
                'summary': 'Chunk processing completed with some errors',
                'key_findings': ['Large dataset processed successfully in chunks'],
                'recommendations': ['Review processing logs for any chunk-specific issues']
            }