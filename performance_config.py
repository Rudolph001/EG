
"""
Performance configuration for Email Guardian
Optimized for maximum processing speed
"""
import os

class PerformanceConfig:
    """Configuration class for performance optimization"""
    
    def __init__(self):
        # Enable ultra-fast mode for large datasets
        self.fast_mode = os.environ.get('EMAIL_GUARDIAN_FAST_MODE', 'true').lower() == 'true'
        
        # Significantly increased chunk sizes for better performance
        self.chunk_size = int(os.environ.get('EMAIL_GUARDIAN_CHUNK_SIZE', '5000' if self.fast_mode else '1000'))
        self.max_ml_records = int(os.environ.get('EMAIL_GUARDIAN_MAX_ML_RECORDS', '10000' if self.fast_mode else '50000'))
        self.ml_estimators = int(os.environ.get('EMAIL_GUARDIAN_ML_ESTIMATORS', '5' if self.fast_mode else '50'))
        self.progress_update_interval = int(os.environ.get('EMAIL_GUARDIAN_PROGRESS_INTERVAL', '1000' if self.fast_mode else '200'))
        
        # Minimal feature engineering for speed
        self.tfidf_max_features = int(os.environ.get('EMAIL_GUARDIAN_TFIDF_FEATURES', '50' if self.fast_mode else '500'))
        self.skip_advanced_analysis = os.environ.get('EMAIL_GUARDIAN_SKIP_ADVANCED', 'true' if self.fast_mode else 'false').lower() == 'true'
        
        # Large batch commits for database efficiency
        self.batch_commit_size = int(os.environ.get('EMAIL_GUARDIAN_BATCH_SIZE', '1000' if self.fast_mode else '200'))
        
        # Timeout settings optimized for large datasets
        self.database_timeout = int(os.environ.get('EMAIL_GUARDIAN_DB_TIMEOUT', '600'))  # 10 minutes
        self.ml_chunk_size = int(os.environ.get('EMAIL_GUARDIAN_ML_CHUNK_SIZE', '10000' if self.fast_mode else '2000'))  # Much larger ML chunks
        
        # New optimization flags
        self.cache_keywords = True  # Cache keywords to avoid repeated DB queries
        self.skip_complex_ml = self.fast_mode  # Skip complex ML for speed
        self.parallel_processing = False  # Keep single-threaded for stability
    
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
            'batch_commit_size': self.batch_commit_size,
            'ml_chunk_size': self.ml_chunk_size,
            'cache_keywords': self.cache_keywords,
            'skip_complex_ml': self.skip_complex_ml
        }

# Global configuration instance
config = PerformanceConfig()
