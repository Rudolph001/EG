# Email Guardian - Email Security Analysis Platform

## Overview

Email Guardian is a comprehensive web application designed for analyzing Tessian email export data. Its primary purpose is to detect security threats, potential data exfiltration attempts, and anomalous communication patterns within an organization's email traffic. The platform achieves this through a combination of rule-based filtering, advanced machine learning analytics, and intelligent domain classification. The project aims to provide enterprise-grade email security analysis, offering capabilities like multi-dimensional risk assessment, detailed reporting, and interactive network visualizations to enhance security posture and facilitate rapid incident response.

## User Preferences

Preferred communication style: Simple, everyday language.

**Documentation Preference**: User prefers visual, easy-to-understand guides with practical implementation steps for complex features like Adaptive ML.

## Database Schema Management Policy

**CRITICAL REQUIREMENT**: Any database schema changes (adding columns, modifying tables, etc.) must be applied to BOTH databases:

1. **PostgreSQL (Production/Replit)**: Use `execute_sql_tool` to modify the production database
2. **SQLite (Local Development)**: Update local database using Python scripts or SQL commands

**Schema Synchronization Tools**:
- `setup_local_database.py` - Complete local database setup
- `force_recreate_local_db.py` - Force recreation of local database  
- `migrate_local_db.py` - Add missing columns to existing local database

**Recent Schema Issues Resolved**:
- Added `account_type` column to both databases (2025-08-06)
- Added flagging columns (`is_flagged`, `flag_reason`, `flagged_at`, `flagged_by`, `previously_flagged`) to both databases
- Enhanced timestamp parsing for format: `2025-08-04T23:58:20.543+0200`

**Recent Improvements (2025-08-06)**:
- ✓ Updated Case Manager case view modal to match Flag Event dashboard format exactly
- ✓ Added "Leaver" badge display for senders who are leavers in grouped email view
- ✓ Implemented Flag Sender functionality that properly updates Flag Event dashboard
- ✓ Enhanced grouped cases API to include leaver status information
- ✓ Added comprehensive sender flagging endpoint (`/api/flag-sender/<session_id>`)
- ✓ Fixed case view modal layout with proper two-column structure and blue section headers
- ✓ **MAJOR: Implemented Advanced Adaptive ML Engine** - Full learning system that adapts to user decisions
- ✓ **NEW: Adaptive ML Dashboard** - Comprehensive analytics showing learning progress and model evolution
- ✓ **NEW: Continuous Learning Loop** - System automatically learns from escalation/clear decisions
- ✓ **ENHANCED: Attachment Analysis** - 15+ advanced features for filename patterns, social engineering detection
- ✓ **NEW: ML Feedback System** - Records all user decisions for continuous model improvement
- ✓ **NEW: Hybrid Scoring** - Combines base Isolation Forest with adaptive learning (10% → 70% adaptive weight)
- ✓ **NEW: Comprehensive Documentation** - Created detailed Adaptive_ML_Guide.md with visual workflow and implementation steps
- ✓ **NEW: Professional Presentation** - Created Email_Guardian_Presentation.md for lunch & learn sessions and executive briefings

## System Architecture

Email Guardian is built on a modular Flask-based architecture, ensuring clear separation of concerns and maintainability.

-   **Frontend**: Utilizes Bootstrap 5 for responsive design, Jinja2 for templating, Chart.js for dynamic data visualizations, and DataTables for advanced data display. It features multiple specialized dashboards (main, sender analysis, time analysis, professional network link, reports) and an administrative panel for system configuration and management. UI/UX emphasizes professional design, interactive elements, and real-time feedback.
-   **Backend**: Developed with the Flask web framework, employing SQLAlchemy ORM for database interactions.
-   **Database**: Dual database architecture - PostgreSQL for production (Replit) and SQLite for local development. **CRITICAL: All database schema changes must be applied to both PostgreSQL and SQLite databases to maintain compatibility between environments.**
-   **ML Engine**: Advanced three-tier machine learning system: (1) Base Isolation Forest for anomaly detection, (2) Advanced ML for pattern recognition, and (3) **NEW: Adaptive ML Engine** that learns from user escalation decisions using SGDClassifier with incremental learning. Features hybrid scoring that adapts from 10% to 70% user-decision weight as confidence grows.
-   **Data Processing**: Handles large CSV datasets efficiently using chunked processing with pandas (2500 records per chunk) and case-insensitive column mapping.
-   **Session Management**: Employs JSON-based data persistence with gzip compression for large session files, allowing for iterative analysis.
-   **Rule Engine**: A configurable system supporting complex AND/OR logic, regex patterns, and various operators for defining business rules and pre-processing exclusion rules.
-   **Domain Classification**: Automated categorization of domains (corporate, personal, public, suspicious) with whitelist management and a multi-factor trust scoring system.
-   **Deployment**: Designed for local deployment on Windows and Mac systems, running with Gunicorn on port 5000. It utilizes a file-based session management system and environment variable-based configuration.

## External Dependencies

-   **Web Framework**: Flask
-   **Database ORM**: SQLAlchemy
-   **Templating Engine**: Jinja2
-   **Data Manipulation**: pandas, numpy
-   **Machine Learning**: scikit-learn
-   **Networking**: networkx
-   **System Utilities**: psutil
-   **UI Framework**: Bootstrap 5
-   **Charting Library**: Chart.js
-   **Table Enhancements**: DataTables
-   **Icons**: Font Awesome
-   **Compression**: gzip
-   **Serialization**: JSON