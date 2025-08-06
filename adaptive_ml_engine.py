import numpy as np
import pandas as pd
import json
import logging
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import SGDClassifier
from sklearn.ensemble import VotingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, roc_auc_score
import joblib
import os
from collections import defaultdict, deque
from models import EmailRecord, ProcessingSession, AdaptiveLearningMetrics, LearningPattern
from app import db
from performance_config import config

logger = logging.getLogger(__name__)

class AdaptiveMLEngine:
    """Advanced ML engine that learns from user escalation decisions"""

    def __init__(self):
        self.base_isolation_forest = IsolationForest(contamination=0.1, n_estimators=config.ml_estimators)
        self.adaptive_classifier = SGDClassifier(
            loss='log_loss', 
            learning_rate='adaptive',
            eta0=0.01,  # Initial learning rate
            random_state=42,
            warm_start=True
        )
        self.is_adaptive_trained = False
        self.tfidf_vectorizer = TfidfVectorizer(max_features=config.tfidf_max_features, stop_words='english')
        self.scaler = StandardScaler()
        
        # Learning tracking
        self.recent_feedback = deque(maxlen=2000)
        self.learning_patterns = defaultdict(list)
        self.performance_history = []
        self.feature_importance = {}
        self.adaptive_weight = 0.1  # Start with 10% adaptive, 90% base model
        
        # Model persistence
        self.models_dir = 'models'
        os.makedirs(self.models_dir, exist_ok=True)
        
        logger.info("AdaptiveMLEngine initialized")

    def get_fast_learning_analytics(self):
        """Fast version of learning analytics for dashboard performance"""
        try:
            from sqlalchemy import text
            
            # Get basic learning counts quickly
            feedback_count = db.session.execute(text('SELECT COUNT(*) FROM ml_feedback')).scalar() or 0
            escalated_count = db.session.execute(text("SELECT COUNT(*) FROM ml_feedback WHERE user_decision = 'Escalated'")).scalar() or 0
            cleared_count = db.session.execute(text("SELECT COUNT(*) FROM ml_feedback WHERE user_decision = 'Cleared'")).scalar() or 0
            
            # Calculate adaptive weight based on feedback
            adaptive_weight = min(0.1 + (feedback_count * 0.006), 0.7)  # 10% to 70%
            
            # Simple performance metrics
            learning_confidence = min(feedback_count * 2, 100) / 100
            model_maturity = 'Initial' if feedback_count < 20 else 'Learning' if feedback_count < 100 else 'Trained'
            
            return {
                'model_evolution': {
                    'improvement_over_time': [],
                    'weight_progression': [{'date': datetime.now().isoformat(), 'weight': adaptive_weight}],
                    'accuracy_trends': []
                },
                'learning_trends': {
                    'learning_sessions': 1 if feedback_count > 0 else 0,
                    'total_decisions_learned': feedback_count,
                    'total_escalations': escalated_count,
                    'total_cleared': cleared_count,
                    'learning_rate': escalated_count / feedback_count if feedback_count > 0 else 0.0
                },
                'decision_patterns': {
                    'escalation_reasons': {},
                    'pattern_analysis': {},
                    'confidence_distribution': []
                },
                'performance_metrics': {
                    'model_trained': feedback_count > 10,
                    'adaptive_weight': adaptive_weight,
                    'learning_confidence': learning_confidence,
                    'latest_session_feedback': feedback_count,
                    'model_maturity': model_maturity
                },
                'feature_insights': {
                    'top_features': [],
                    'feature_weights': {},
                    'correlation_matrix': []
                },
                'recommendations': [
                    'Continue making escalation/clear decisions to improve model accuracy',
                    f'Current adaptive weight: {adaptive_weight:.1%} (grows with more decisions)',
                    f'Model maturity: {model_maturity} with {feedback_count} decisions recorded'
                ]
            }
            
        except Exception as e:
            logger.error(f"Error in fast learning analytics: {str(e)}")
            # Return minimal fallback
            return {
                'model_evolution': {'improvement_over_time': [], 'weight_progression': [], 'accuracy_trends': []},
                'learning_trends': {'learning_sessions': 0, 'total_decisions_learned': 0, 'total_escalations': 0, 'total_cleared': 0, 'learning_rate': 0.0},
                'decision_patterns': {'escalation_reasons': {}, 'pattern_analysis': {}, 'confidence_distribution': []},
                'performance_metrics': {'model_trained': False, 'adaptive_weight': 0.1, 'learning_confidence': 0.0, 'latest_session_feedback': 0, 'model_maturity': 'Initial'},
                'feature_insights': {'top_features': [], 'feature_weights': {}, 'correlation_matrix': []},
                'recommendations': ['Error loading analytics - using fallback data']
            }

    def analyze_session_with_learning(self, session_id):
        """Perform ML analysis with adaptive learning capabilities"""
        try:
            logger.info(f"Starting adaptive ML analysis for session {session_id}")
            
            # Load existing models if available
            self._load_models()
            
            # Get records for analysis
            records = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.excluded_by_rule.is_(None),
                db.or_(EmailRecord.whitelisted.is_(None), EmailRecord.whitelisted == False)
            ).all()
            
            if not records:
                return self._empty_analysis_result()
            
            # Convert to DataFrame for analysis
            df = self._records_to_enhanced_dataframe(records)
            
            # Engineer features for both base and adaptive models
            base_features = self._engineer_base_features(df)
            adaptive_features = self._engineer_adaptive_features(df)
            
            # Apply base model (Isolation Forest)
            base_scores = self._apply_base_model(base_features)
            
            # Apply adaptive model if trained
            adaptive_scores = self._apply_adaptive_model(adaptive_features)
            
            # Combine scores using learned weights
            final_scores, risk_levels = self._combine_model_outputs(base_scores, adaptive_scores)
            
            # Update records with results
            self._update_records_with_scores(records, final_scores, risk_levels, adaptive_features)
            
            # Track analysis metrics
            analysis_metrics = self._calculate_analysis_metrics(records, final_scores)
            
            # Learn from any available feedback
            self._learn_from_recent_feedback(session_id)
            
            db.session.commit()
            
            logger.info(f"Adaptive ML analysis completed for session {session_id}")
            return analysis_metrics
            
        except Exception as e:
            logger.error(f"Error in adaptive ML analysis: {str(e)}")
            db.session.rollback()
            raise

    def learn_from_user_decisions(self, session_id):
        """Learn from user escalation/clear decisions"""
        try:
            logger.info(f"Learning from user decisions for session {session_id}")
            
            # Get records with user decisions
            feedback_records = EmailRecord.query.filter(
                EmailRecord.session_id == session_id,
                EmailRecord.case_status.in_(['Cleared', 'Escalated'])
            ).all()
            
            if len(feedback_records) < 10:  # Need minimum feedback
                logger.info(f"Insufficient feedback: {len(feedback_records)} decisions")
                return False
            
            # Prepare training data
            X_feedback, y_feedback = self._prepare_feedback_data(feedback_records)
            
            if len(X_feedback) == 0:
                return False
            
            # Train/update adaptive model
            if not self.is_adaptive_trained:
                self.adaptive_classifier.fit(X_feedback, y_feedback)
                self.is_adaptive_trained = True
                logger.info("Adaptive classifier trained for first time")
            else:
                self.adaptive_classifier.partial_fit(X_feedback, y_feedback)
                logger.info("Adaptive classifier updated with new feedback")
            
            # Update learning patterns
            self._analyze_learning_patterns(feedback_records)
            
            # Evaluate and adjust model weights
            self._evaluate_and_adjust_weights(feedback_records)
            
            # Save updated models
            self._save_models()
            
            # Store learning metrics
            self._store_learning_metrics(session_id, feedback_records)
            
            logger.info(f"Learning completed: {len(feedback_records)} decisions processed")
            return True
            
        except Exception as e:
            logger.error(f"Error learning from decisions: {str(e)}")
            return False

    def _records_to_enhanced_dataframe(self, records):
        """Convert records to DataFrame with enhanced features"""
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
                'bunit': record.bunit or '',
                'account_type': getattr(record, 'account_type', '') or '',
                'case_status': record.case_status or 'Active',
                'ml_risk_score': record.ml_risk_score or 0.0
            })
        return pd.DataFrame(data)

    def _engineer_adaptive_features(self, df):
        """Engineer advanced features for adaptive learning"""
        features = []
        
        for _, row in df.iterrows():
            feature_vector = []
            
            # Enhanced attachment analysis
            attachment_features = self._extract_attachment_features(row['attachments'])
            feature_vector.extend(attachment_features)
            
            # Sender behavior patterns
            sender_features = self._extract_sender_features(row['sender'])
            feature_vector.extend(sender_features)
            
            # Content analysis features
            content_features = self._extract_content_features(row['subject'], row['attachments'])
            feature_vector.extend(content_features)
            
            # Temporal features
            temporal_features = self._extract_temporal_features(row['time'])
            feature_vector.extend(temporal_features)
            
            # Department/context features
            context_features = self._extract_context_features(row)
            feature_vector.extend(context_features)
            
            features.append(feature_vector)
        
        return np.array(features)

    def _extract_attachment_features(self, attachments):
        """Extract detailed attachment features"""
        if not attachments:
            return [0] * 15  # Return zero vector for no attachments
        
        attachments_lower = attachments.lower()
        features = []
        
        # File extension analysis
        high_risk_exts = ['.exe', '.scr', '.bat', '.cmd', '.com', '.pif', '.vbs', '.js']
        medium_risk_exts = ['.zip', '.rar', '.7z', '.doc', '.docx', '.xls', '.xlsx', '.pdf']
        
        features.append(sum(1 for ext in high_risk_exts if ext in attachments_lower))
        features.append(sum(1 for ext in medium_risk_exts if ext in attachments_lower))
        
        # Filename patterns
        features.append(1 if any(p in attachments_lower for p in ['confidential', 'urgent', 'invoice']) else 0)
        features.append(1 if 'double extension' in attachments_lower else 0)
        features.append(len(attachments.split(',')) if ',' in attachments else 1)  # Number of attachments
        
        # Social engineering indicators
        features.append(1 if any(p in attachments_lower for p in ['payment', 'bill', 'receipt']) else 0)
        features.append(1 if any(p in attachments_lower for p in ['personal', 'private', 'secret']) else 0)
        
        # Filename entropy (randomness)
        entropy = self._calculate_filename_entropy(attachments)
        features.append(entropy)
        
        # Size indicators (if available in filename)
        features.append(1 if any(s in attachments_lower for s in ['mb', 'gb', 'large']) else 0)
        
        # Archive indicators
        features.append(1 if any(a in attachments_lower for a in ['zip', 'rar', '7z', 'tar']) else 0)
        
        # Password protection indicators
        features.append(1 if any(p in attachments_lower for p in ['password', 'protected', 'encrypted']) else 0)
        
        # Executable disguised as document
        features.append(1 if any(e in attachments_lower for e in high_risk_exts) and any(d in attachments_lower for d in ['doc', 'pdf', 'txt']) else 0)
        
        # Timestamp in filename
        features.append(1 if any(t in attachments for t in ['2024', '2025', '202']) else 0)
        
        # Multiple extensions
        features.append(attachments.count('.') - 1 if '.' in attachments else 0)
        
        # Unicode or special characters
        features.append(1 if any(ord(c) > 127 for c in attachments) else 0)
        
        return features

    def _extract_sender_features(self, sender):
        """Extract sender-specific features"""
        features = []
        
        if not sender:
            return [0] * 8
        
        sender_lower = sender.lower()
        
        # Domain analysis
        if '@' in sender:
            domain = sender.split('@')[1] if '@' in sender else ''
            features.append(1 if any(d in domain for d in ['gmail.com', 'yahoo.com', 'hotmail.com']) else 0)
            features.append(1 if domain.endswith('.com') else 0)
            features.append(1 if any(corp in domain for corp in ['company', 'corp', 'enterprise']) else 0)
        else:
            features.extend([0, 0, 0])
        
        # Sender name patterns
        features.append(1 if any(c.isdigit() for c in sender) else 0)  # Contains numbers
        features.append(len(sender.split('.')) - 1)  # Dots in email
        features.append(1 if '_' in sender or '-' in sender else 0)  # Special characters
        features.append(len(sender))  # Email length
        features.append(1 if sender.count('@') > 1 else 0)  # Multiple @ symbols
        
        return features

    def _extract_content_features(self, subject, attachments):
        """Extract content-based features"""
        features = []
        
        combined_text = f"{subject or ''} {attachments or ''}".lower()
        
        # Urgency indicators
        urgency_words = ['urgent', 'asap', 'immediate', 'rush', 'emergency']
        features.append(sum(1 for word in urgency_words if word in combined_text))
        
        # Financial indicators
        financial_words = ['payment', 'invoice', 'bill', 'money', 'transfer', 'account']
        features.append(sum(1 for word in financial_words if word in combined_text))
        
        # Personal indicators
        personal_words = ['personal', 'private', 'confidential', 'secret']
        features.append(sum(1 for word in personal_words if word in combined_text))
        
        # Authority indicators
        authority_words = ['ceo', 'manager', 'director', 'admin', 'official']
        features.append(sum(1 for word in authority_words if word in combined_text))
        
        # Text length features
        features.append(len(subject or ''))
        features.append(len(attachments or ''))
        
        # Capital letter ratio
        if subject:
            features.append(sum(1 for c in subject if c.isupper()) / len(subject))
        else:
            features.append(0)
        
        return features

    def _extract_temporal_features(self, time_str):
        """Extract time-based features"""
        features = []
        
        if not time_str:
            return [0] * 5
        
        try:
            # Basic time analysis (can be enhanced with proper parsing)
            time_lower = time_str.lower()
            
            # Weekend indicator
            features.append(1 if any(day in time_lower for day in ['saturday', 'sunday', 'weekend']) else 0)
            
            # After hours (rough estimation)
            features.append(1 if any(hour in time_str for hour in ['22:', '23:', '00:', '01:', '02:', '03:', '04:', '05:']) else 0)
            
            # Early morning
            features.append(1 if any(hour in time_str for hour in ['06:', '07:', '08:']) else 0)
            
            # Business hours
            features.append(1 if any(hour in time_str for hour in ['09:', '10:', '11:', '14:', '15:', '16:', '17:']) else 0)
            
            # Contains date/time info
            features.append(1 if any(d in time_str for d in ['2024', '2025', ':']) else 0)
            
        except Exception:
            features = [0] * 5
        
        return features

    def _extract_context_features(self, row):
        """Extract contextual features"""
        features = []
        
        # Leaver status
        features.append(1 if row['leaver'].lower() in ['yes', 'true', '1'] else 0)
        
        # Department risk (simplified)
        high_risk_depts = ['finance', 'hr', 'admin', 'executive']
        features.append(1 if any(dept in row['department'].lower() for dept in high_risk_depts) else 0)
        
        # Business unit context
        features.append(1 if row['bunit'] else 0)
        
        # Account type
        features.append(1 if 'admin' in row['account_type'].lower() else 0)
        
        # Has justification
        features.append(1 if row['justification'] else 0)
        features.append(len(row['justification']) if row['justification'] else 0)
        
        return features

    def _calculate_filename_entropy(self, filename):
        """Calculate entropy of filename to detect randomness"""
        if not filename:
            return 0
        
        # Simple entropy calculation
        char_counts = defaultdict(int)
        for char in filename.lower():
            char_counts[char] += 1
        
        total_chars = len(filename)
        entropy = 0
        for count in char_counts.values():
            probability = count / total_chars
            if probability > 0:
                entropy -= probability * np.log2(probability)
        
        return entropy

    def _prepare_feedback_data(self, feedback_records):
        """Convert user decisions to training data"""
        df = self._records_to_enhanced_dataframe(feedback_records)
        X = self._engineer_adaptive_features(df)
        
        # Convert decisions to labels (1 = Escalated, 0 = Cleared)
        y = []
        for record in feedback_records:
            if record.case_status == 'Escalated':
                y.append(1)
            elif record.case_status == 'Cleared':
                y.append(0)
        
        return X, np.array(y)

    def _combine_model_outputs(self, base_scores, adaptive_scores):
        """Combine base and adaptive model outputs"""
        if adaptive_scores is None or not self.is_adaptive_trained:
            # Use only base model
            final_scores = base_scores
        else:
            # Weighted combination
            final_scores = (1 - self.adaptive_weight) * base_scores + self.adaptive_weight * adaptive_scores
        
        # Convert to risk levels
        risk_levels = []
        for score in final_scores:
            if score >= 0.8:
                risk_levels.append('Critical')
            elif score >= 0.6:
                risk_levels.append('High')
            elif score >= 0.4:
                risk_levels.append('Medium')
            else:
                risk_levels.append('Low')
        
        return final_scores, risk_levels

    def _apply_base_model(self, features):
        """Apply base Isolation Forest model"""
        try:
            if features.shape[0] == 0:
                return np.array([])
            
            # Fit and predict with Isolation Forest
            anomaly_scores = self.base_isolation_forest.fit_predict(features)
            decision_scores = self.base_isolation_forest.decision_function(features)
            
            # Convert to 0-1 scale
            normalized_scores = (decision_scores - decision_scores.min()) / (decision_scores.max() - decision_scores.min() + 1e-8)
            
            return normalized_scores
            
        except Exception as e:
            logger.error(f"Error in base model: {str(e)}")
            return np.full(features.shape[0], 0.5)

    def _apply_adaptive_model(self, features):
        """Apply adaptive classifier if trained"""
        if not self.is_adaptive_trained or features.shape[0] == 0:
            return None
        
        try:
            # Get probability scores
            scores = self.adaptive_classifier.predict_proba(features)[:, 1]
            return scores
        except Exception as e:
            logger.error(f"Error in adaptive model: {str(e)}")
            return None

    def _update_records_with_scores(self, records, scores, risk_levels, features):
        """Update records with ML scores and explanations"""
        for i, record in enumerate(records):
            record.ml_risk_score = float(scores[i])
            record.risk_level = risk_levels[i]
            
            # Generate explanation
            explanation = self._generate_explanation(features[i], scores[i], risk_levels[i])
            record.ml_explanation = explanation

    def _generate_explanation(self, feature_vector, score, risk_level):
        """Generate human-readable explanation for the ML decision"""
        explanations = []
        
        # This is a simplified explanation generator
        # In practice, you'd map feature indices to meanings
        
        if score >= 0.8:
            explanations.append("High anomaly score detected")
        elif score >= 0.6:
            explanations.append("Moderate risk indicators present")
        
        if self.is_adaptive_trained:
            explanations.append(f"Adaptive model confidence: {self.adaptive_weight:.1%}")
        
        return f"{risk_level} risk: " + "; ".join(explanations)

    def _analyze_learning_patterns(self, feedback_records):
        """Analyze patterns in user feedback"""
        escalated = [r for r in feedback_records if r.case_status == 'Escalated']
        cleared = [r for r in feedback_records if r.case_status == 'Cleared']
        
        # Store learning patterns for analytics
        patterns = {
            'escalated_count': len(escalated),
            'cleared_count': len(cleared),
            'escalation_rate': len(escalated) / len(feedback_records) if feedback_records else 0,
            'patterns': self._identify_decision_patterns(escalated, cleared)
        }
        
        self.learning_patterns[datetime.now().date()] = patterns

    def _identify_decision_patterns(self, escalated, cleared):
        """Identify patterns in escalation vs clearing decisions"""
        patterns = {
            'escalated_senders': [r.sender for r in escalated],
            'escalated_domains': [r.recipients_email_domain for r in escalated],
            'escalated_with_attachments': sum(1 for r in escalated if r.attachments),
            'cleared_with_attachments': sum(1 for r in cleared if r.attachments),
        }
        return patterns

    def _evaluate_and_adjust_weights(self, feedback_records):
        """Evaluate model performance and adjust weights"""
        if len(feedback_records) < 20:
            return
        
        try:
            # Prepare data for evaluation
            X, y_true = self._prepare_feedback_data(feedback_records)
            
            # Get predictions from both models
            base_pred = self.base_isolation_forest.decision_function(X)
            
            if self.is_adaptive_trained:
                adaptive_pred = self.adaptive_classifier.predict_proba(X)[:, 1]
                
                # Evaluate both models
                base_auc = roc_auc_score(y_true, base_pred)
                adaptive_auc = roc_auc_score(y_true, adaptive_pred)
                
                # Adjust weights based on performance
                if adaptive_auc > base_auc:
                    self.adaptive_weight = min(0.7, self.adaptive_weight + 0.05)
                else:
                    self.adaptive_weight = max(0.1, self.adaptive_weight - 0.02)
                
                logger.info(f"Model performance - Base AUC: {base_auc:.3f}, Adaptive AUC: {adaptive_auc:.3f}, Weight: {self.adaptive_weight:.3f}")
                
        except Exception as e:
            logger.error(f"Error evaluating models: {str(e)}")

    def _store_learning_metrics(self, session_id, feedback_records):
        """Store learning metrics in database"""
        try:
            metrics = AdaptiveLearningMetrics(
                session_id=session_id,
                feedback_count=len(feedback_records),
                escalated_count=sum(1 for r in feedback_records if r.case_status == 'Escalated'),
                cleared_count=sum(1 for r in feedback_records if r.case_status == 'Cleared'),
                adaptive_weight=self.adaptive_weight,
                model_performance=self._calculate_current_performance(),
                learning_patterns=json.dumps(self.learning_patterns.get(datetime.now().date(), {})),
                created_at=datetime.utcnow()
            )
            db.session.add(metrics)
            db.session.commit()
        except Exception as e:
            logger.error(f"Error storing learning metrics: {str(e)}")

    def _calculate_current_performance(self):
        """Calculate current model performance metrics"""
        # Return basic performance info
        return {
            'adaptive_trained': self.is_adaptive_trained,
            'adaptive_weight': self.adaptive_weight,
            'feedback_samples': len(self.recent_feedback)
        }

    def _save_models(self):
        """Save trained models to disk"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if self.is_adaptive_trained:
                joblib.dump(self.adaptive_classifier, f'{self.models_dir}/adaptive_model_{timestamp}.pkl')
            
            joblib.dump(self.base_isolation_forest, f'{self.models_dir}/base_model_{timestamp}.pkl')
            
            # Save configuration
            config_data = {
                'adaptive_weight': self.adaptive_weight,
                'is_adaptive_trained': self.is_adaptive_trained,
                'timestamp': timestamp
            }
            
            with open(f'{self.models_dir}/config_{timestamp}.json', 'w') as f:
                json.dump(config_data, f)
                
        except Exception as e:
            logger.error(f"Error saving models: {str(e)}")

    def _load_models(self):
        """Load latest trained models"""
        try:
            if not os.path.exists(self.models_dir):
                return
            
            # Find latest models
            config_files = [f for f in os.listdir(self.models_dir) if f.startswith('config_') and f.endswith('.json')]
            if not config_files:
                return
            
            latest_config = sorted(config_files)[-1]
            timestamp = latest_config.replace('config_', '').replace('.json', '')
            
            # Load configuration
            with open(f'{self.models_dir}/{latest_config}', 'r') as f:
                config_data = json.load(f)
            
            self.adaptive_weight = config_data.get('adaptive_weight', 0.1)
            self.is_adaptive_trained = config_data.get('is_adaptive_trained', False)
            
            # Load models
            adaptive_path = f'{self.models_dir}/adaptive_model_{timestamp}.pkl'
            base_path = f'{self.models_dir}/base_model_{timestamp}.pkl'
            
            if os.path.exists(adaptive_path) and self.is_adaptive_trained:
                self.adaptive_classifier = joblib.load(adaptive_path)
                logger.info(f"Loaded adaptive model from {timestamp}")
            
            if os.path.exists(base_path):
                self.base_isolation_forest = joblib.load(base_path)
                logger.info(f"Loaded base model from {timestamp}")
                
        except Exception as e:
            logger.error(f"Error loading models: {str(e)}")

    def get_learning_analytics(self, days=30):
        """Get comprehensive learning analytics"""
        try:
            # Get recent learning metrics
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            metrics = AdaptiveLearningMetrics.query.filter(
                AdaptiveLearningMetrics.created_at >= cutoff_date
            ).order_by(AdaptiveLearningMetrics.created_at.desc()).all()
            
            # Calculate analytics
            analytics = {
                'model_evolution': self._analyze_model_evolution(metrics),
                'learning_trends': self._analyze_learning_trends(metrics),
                'decision_patterns': self._analyze_decision_patterns(metrics),
                'performance_metrics': self._calculate_performance_metrics(metrics),
                'feature_insights': self._get_feature_insights(),
                'recommendations': self._generate_recommendations(metrics)
            }
            
            return analytics
            
        except Exception as e:
            logger.error(f"Error getting learning analytics: {str(e)}")
            return {}

    def _analyze_model_evolution(self, metrics):
        """Analyze how the model has evolved over time"""
        evolution = []
        for metric in metrics:
            evolution.append({
                'date': metric.created_at.strftime('%Y-%m-%d'),
                'adaptive_weight': metric.adaptive_weight,
                'feedback_count': metric.feedback_count,
                'escalation_rate': metric.escalated_count / metric.feedback_count if metric.feedback_count > 0 else 0
            })
        return evolution

    def _analyze_learning_trends(self, metrics):
        """Analyze learning trends and patterns"""
        if not metrics:
            return {}
        
        total_feedback = sum(m.feedback_count for m in metrics)
        total_escalated = sum(m.escalated_count for m in metrics)
        
        return {
            'total_decisions_learned': total_feedback,
            'total_escalations': total_escalated,
            'avg_escalation_rate': total_escalated / total_feedback if total_feedback > 0 else 0,
            'learning_sessions': len(metrics),
            'current_adaptive_weight': self.adaptive_weight
        }

    def _analyze_decision_patterns(self, metrics):
        """Analyze patterns in user decisions"""
        patterns = {}
        
        for metric in metrics:
            try:
                if metric.learning_patterns:
                    session_patterns = json.loads(metric.learning_patterns)
                    # Aggregate patterns across sessions
                    for key, value in session_patterns.items():
                        if key not in patterns:
                            patterns[key] = []
                        patterns[key].append(value)
            except Exception:
                continue
        
        return patterns

    def _calculate_performance_metrics(self, metrics):
        """Calculate overall performance metrics"""
        if not metrics:
            return {}
        
        latest = metrics[0] if metrics else None
        
        return {
            'model_trained': self.is_adaptive_trained,
            'adaptive_weight': self.adaptive_weight,
            'learning_confidence': min(1.0, len(metrics) / 10),  # Confidence based on sessions
            'latest_session_feedback': latest.feedback_count if latest else 0,
            'model_maturity': 'Advanced' if self.adaptive_weight > 0.5 else 'Learning' if self.adaptive_weight > 0.2 else 'Initial'
        }

    def _get_feature_insights(self):
        """Get insights about feature importance and patterns"""
        # This would contain learned feature importance
        return {
            'top_risk_indicators': ['High-risk attachments', 'External domains', 'After-hours activity'],
            'learned_patterns': ['Leaver + attachments = high risk', 'PDF invoices = medium risk'],
            'adaptive_features': 'Attachment patterns, sender behavior, temporal context'
        }

    def _generate_recommendations(self, metrics):
        """Generate recommendations for improving the system"""
        recommendations = []
        
        if not self.is_adaptive_trained:
            recommendations.append("Process more email sessions to enable adaptive learning")
        elif self.adaptive_weight < 0.3:
            recommendations.append("Continue providing feedback to improve adaptive model confidence")
        elif len(metrics) < 5:
            recommendations.append("Analyze more sessions to identify stronger patterns")
        else:
            recommendations.append("Model is learning well - consider expanding to new risk categories")
        
        return recommendations

    def _engineer_base_features(self, df):
        """Engineer basic features for base model compatibility"""
        features = []
        
        for _, row in df.iterrows():
            feature_vector = [
                len(row['subject']),
                1 if row['attachments'] else 0,
                1 if row['leaver'].lower() in ['yes', 'true', '1'] else 0,
                len(row['justification']) if row['justification'] else 0,
                1 if any(domain in row['recipients_email_domain'].lower() for domain in ['gmail.com', 'yahoo.com']) else 0
            ]
            features.append(feature_vector)
        
        return np.array(features)

    def _learn_from_recent_feedback(self, session_id):
        """Learn from recent feedback if available"""
        recent_feedback = EmailRecord.query.filter(
            EmailRecord.session_id == session_id,
            EmailRecord.case_status.in_(['Cleared', 'Escalated']),
            EmailRecord.resolved_at >= datetime.utcnow() - timedelta(hours=24)
        ).all()
        
        if recent_feedback:
            self.learn_from_user_decisions(session_id)

    def _empty_analysis_result(self):
        """Return empty analysis result"""
        return {
            'processing_stats': {
                'ml_records_analyzed': 0,
                'anomalies_detected': 0,
                'critical_cases': 0,
                'high_risk_cases': 0
            },
            'insights': {'message': 'No records to analyze'}
        }

    def _calculate_analysis_metrics(self, records, scores):
        """Calculate metrics for the analysis session"""
        return {
            'processing_stats': {
                'ml_records_analyzed': len(records),
                'anomalies_detected': sum(1 for s in scores if s > 0.7),
                'critical_cases': sum(1 for r in records if r.risk_level == 'Critical'),
                'high_risk_cases': sum(1 for r in records if r.risk_level == 'High'),
                'adaptive_weight_used': self.adaptive_weight,
                'adaptive_model_active': self.is_adaptive_trained
            },
            'insights': {
                'summary': f'Adaptive ML analysis completed for {len(records)} records',
                'adaptive_learning': f'Model weight: {self.adaptive_weight:.1%}',
                'learning_status': 'Active' if self.is_adaptive_trained else 'Training'
            }
        }