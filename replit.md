# Email Guardian - Email Security Analysis Platform

## Overview

Email Guardian is a comprehensive web application designed for analyzing Tessian email export data. Its primary purpose is to detect security threats, potential data exfiltration attempts, and anomalous communication patterns within an organization's email traffic. The platform achieves this through a combination of rule-based filtering, advanced machine learning analytics, and intelligent domain classification. The project aims to provide enterprise-grade email security analysis, offering capabilities like multi-dimensional risk assessment, detailed reporting, and interactive network visualizations to enhance security posture and facilitate rapid incident response.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

Email Guardian is built on a modular Flask-based architecture, ensuring clear separation of concerns and maintainability.

-   **Frontend**: Utilizes Bootstrap 5 for responsive design, Jinja2 for templating, Chart.js for dynamic data visualizations, and DataTables for advanced data display. It features multiple specialized dashboards (main, sender analysis, time analysis, professional network link, reports) and an administrative panel for system configuration and management. UI/UX emphasizes professional design, interactive elements, and real-time feedback.
-   **Backend**: Developed with the Flask web framework, employing SQLAlchemy ORM for database interactions.
-   **Database**: Primarily uses SQLite for development and local deployments, with the architecture designed to support seamless migration to PostgreSQL for production environments.
-   **ML Engine**: Integrates scikit-learn for core machine learning functionalities, including Isolation Forest for anomaly detection, clustering, and pattern recognition. It also includes an advanced ML engine for deeper analytics.
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