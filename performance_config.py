"""
Performance configuration for Email Guardian
Optimizes processing speed for different environments
"""
import os

class PerformanceConfig:
    """Configuration class for performance optimization"""
    
    def __init__(self):
        # Enable fast mode by default for local environments
        self.fast_mode = os.environ.get('EMAIL_GUARDIAN_FAST_MODE', 'true').lower() == 'true'
        
        # Processing parameters
        self.chunk_size = int(os.environ.get('EMAIL_GUARDIAN_CHUNK_SIZE', '1000' if self.fast_mode else '500'))
        self.max_ml_records = int(os.environ.get('EMAIL_GUARDIAN_MAX_ML_RECORDS', '20000' if self.fast_mode else '50000'))
        self.ml_estimators = int(os.environ.get('EMAIL_GUARDIAN_ML_ESTIMATORS', '50' if self.fast_mode else '100'))
        self.progress_update_interval = int(os.environ.get('EMAIL_GUARDIAN_PROGRESS_INTERVAL', '500' if self.fast_mode else '100'))
        
        # Feature engineering settings
        self.tfidf_max_features = int(os.environ.get('EMAIL_GUARDIAN_TFIDF_FEATURES', '500' if self.fast_mode else '1000'))
        self.skip_advanced_analysis = os.environ.get('EMAIL_GUARDIAN_SKIP_ADVANCED', 'true' if self.fast_mode else 'false').lower() == 'true'
        
        # Database settings
        self.batch_commit_size = int(os.environ.get('EMAIL_GUARDIAN_BATCH_SIZE', '100' if self.fast_mode else '50'))
    
    def get_config_summary(self):
        """Return configuration summary for logging"""
        return {
            'fast_mode': self.fast_mode,
            'chunk_size': self.chunk_size,
            'max_ml_records': self.max_ml_records,
            'ml_estimators': self.ml_estimators,
            'progress_update_interval': self.progress_update_interval,
            'tfidf_max_features': self.tfidf_max_features,
            'skip_advanced_analysis': self.skip_advanced_analysis,
            'batch_commit_size': self.batch_commit_size
        }

# Global configuration instance
config = PerformanceConfig()