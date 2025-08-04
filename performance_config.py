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
        
        # Processing parameters - optimized for large datasets
        self.chunk_size = int(os.environ.get('EMAIL_GUARDIAN_CHUNK_SIZE', '2000' if self.fast_mode else '500'))
        self.max_ml_records = int(os.environ.get('EMAIL_GUARDIAN_MAX_ML_RECORDS', '100000' if self.fast_mode else '50000'))
        self.ml_estimators = int(os.environ.get('EMAIL_GUARDIAN_ML_ESTIMATORS', '10' if self.fast_mode else '100'))
        self.progress_update_interval = int(os.environ.get('EMAIL_GUARDIAN_PROGRESS_INTERVAL', '500' if self.fast_mode else '100'))
        
        # Feature engineering settings
        self.tfidf_max_features = int(os.environ.get('EMAIL_GUARDIAN_TFIDF_FEATURES', '200' if self.fast_mode else '1000'))
        self.skip_advanced_analysis = os.environ.get('EMAIL_GUARDIAN_SKIP_ADVANCED', 'true' if self.fast_mode else 'false').lower() == 'true'
        
        # Database settings - optimized for large datasets
        self.batch_commit_size = int(os.environ.get('EMAIL_GUARDIAN_BATCH_SIZE', '500' if self.fast_mode else '50'))
        
        # Timeout settings for large datasets
        self.database_timeout = int(os.environ.get('EMAIL_GUARDIAN_DB_TIMEOUT', '300'))  # 5 minutes
        self.ml_chunk_size = int(os.environ.get('EMAIL_GUARDIAN_ML_CHUNK_SIZE', '5000' if self.fast_mode else '2000'))  # Process ML in larger chunks for speed
    
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