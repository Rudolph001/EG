
/**
 * Professional Workflow Progress Management for Email Guardian
 * Enhanced 8-stage processing workflow display and interactions
 */

class WorkflowManager {
    constructor(sessionId) {
        this.sessionId = sessionId;
        this.updateInterval = null;
        this.isPolling = false;
        this.lastUpdateTime = Date.now();
        this.animationQueue = [];
    }

    /**
     * Initialize professional workflow display
     */
    initializeWorkflow() {
        const workflowContainer = document.getElementById('workflowContainer');
        if (!workflowContainer) {
            console.warn('Workflow container not found');
            return;
        }

        const workflowHtml = `
            <div class="workflow-progress-section">
                <div class="workflow-header">
                    <h5 class="workflow-title">
                        <i class="fas fa-cogs"></i>
                        Processing Workflow
                    </h5>
                    <div class="workflow-controls">
                        <span id="workflowStatus" class="workflow-status-badge bg-secondary">Initializing</span>
                        <span id="overallProgress" class="workflow-progress-badge">0%</span>
                    </div>
                </div>
                
                <!-- Enhanced Overall Progress Bar -->
                <div class="workflow-overall-progress">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <span class="text-muted fw-semibold">Overall Progress</span>
                        <span id="progressTimeEstimate" class="text-muted small"></span>
                    </div>
                    <div class="progress">
                        <div id="overallProgressBar" class="progress-bar" 
                             role="progressbar" style="width: 0%" 
                             aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                        </div>
                    </div>
                </div>
                
                <!-- Professional Workflow Stages Grid -->
                <div class="workflow-stages" id="workflowStages">
                    <!-- Stages will be populated dynamically -->
                </div>
            </div>
        `;

        workflowContainer.innerHTML = workflowHtml;
        this.loadWorkflowStatus();
    }

    /**
     * Load current workflow status from API with error handling
     */
    async loadWorkflowStatus() {
        try {
            const response = await fetch(`/api/workflow/${this.sessionId}/status`);
            const data = await response.json();

            if (data.error) {
                console.error('Error loading workflow status:', data.error);
                this.handleWorkflowError(data.error);
                return;
            }

            this.updateWorkflowDisplay(data);
            
            // Start polling if processing
            if (data.status === 'processing' && !this.isPolling) {
                this.startPolling();
            } else if (data.status === 'completed') {
                this.handleWorkflowComplete(data);
            }
        } catch (error) {
            console.error('Error fetching workflow status:', error);
            this.handleWorkflowError('Network error occurred');
        }
    }

    /**
     * Update workflow display with enhanced animations and styling
     */
    updateWorkflowDisplay(workflowData) {
        const { current_stage, overall_progress, status, stages, estimated_time_remaining } = workflowData;

        // Update overall status and progress with animations
        this.updateOverallStatus(status, overall_progress, estimated_time_remaining);
        
        // Update individual stages with professional styling
        this.updateStagesDisplay(stages, current_stage);
    }

    /**
     * Update overall status with professional styling
     */
    updateOverallStatus(status, progress, estimatedTime) {
        const statusElement = document.getElementById('workflowStatus');
        const progressElement = document.getElementById('overallProgress');
        const progressBar = document.getElementById('overallProgressBar');
        const timeEstimate = document.getElementById('progressTimeEstimate');

        if (statusElement) {
            const statusClass = this.getStatusClass(status);
            const statusText = this.getStatusText(status);
            
            statusElement.className = `workflow-status-badge ${statusClass}`;
            statusElement.innerHTML = `<i class="${this.getStatusIcon(status)}"></i> ${statusText}`;
        }

        if (progressElement) {
            const roundedProgress = Math.round(progress);
            if (progressElement.textContent !== `${roundedProgress}%`) {
                this.animateCounter(progressElement, roundedProgress, '%');
            }
        }

        if (progressBar) {
            this.animateProgressBar(progressBar, progress);
        }

        if (timeEstimate && estimatedTime) {
            timeEstimate.textContent = `Est. ${this.formatTimeRemaining(estimatedTime)}`;
        }
    }

    /**
     * Update individual stages with professional styling and animations
     */
    updateStagesDisplay(stages, currentStage) {
        const stagesContainer = document.getElementById('workflowStages');
        if (!stagesContainer || !stages) return;

        const stageDefinitions = this.getStageDefinitions();
        let stagesHtml = '';

        for (let i = 1; i <= 8; i++) {
            const stage = stages[i.toString()];
            const definition = stageDefinitions[i-1];
            
            if (!stage || !definition) continue;

            const stageStatus = stage.status || 'waiting';
            const isActive = i === currentStage;
            const stageClass = this.getStageClass(stageStatus, isActive);
            const icon = this.getStageIcon(definition, stageStatus);

            stagesHtml += `
                <div class="stage-card ${stageClass}" data-stage="${i}">
                    <div class="stage-header">
                        <div class="stage-icon-container">
                            <div class="stage-icon">
                                ${icon}
                            </div>
                            <div class="stage-number">${i}</div>
                        </div>
                    </div>
                    <div class="stage-content">
                        <h6 class="stage-title">${definition.name}</h6>
                        <p class="stage-description">${definition.description}</p>
                        <div class="stage-progress">
                            <div class="stage-progress-bar-container">
                                <div class="progress">
                                    <div class="progress-bar" style="width: ${stage.progress || 0}%"></div>
                                </div>
                            </div>
                            <div class="stage-progress-text">
                                <span>${stage.progress || 0}% Complete</span>
                                ${stage.records_processed ? `<span>${stage.records_processed} processed</span>` : ''}
                            </div>
                        </div>
                        <div class="stage-status status-${stageStatus}">
                            ${this.getStageStatusContent(stage, stageStatus)}
                        </div>
                    </div>
                </div>
            `;
        }

        stagesContainer.innerHTML = stagesHtml;
        
        // Add stagger animation to cards
        this.addStaggerAnimation();
    }

    /**
     * Get stage definitions with professional descriptions
     */
    getStageDefinitions() {
        return [
            {
                name: 'Data Ingestion',
                description: 'Loading and parsing CSV file with validation',
                icon: 'fas fa-upload'
            },
            {
                name: 'Exclusion Rules',
                description: 'Applying exclusion rules and filters',
                icon: 'fas fa-filter'
            },
            {
                name: 'Whitelist Filtering',
                description: 'Processing domain whitelist',
                icon: 'fas fa-shield-alt'
            },
            {
                name: 'Security Rules',
                description: 'Applying security rules engine',
                icon: 'fas fa-gavel'
            },
            {
                name: 'Wordlist Analysis',
                description: 'Analyzing keywords and content',
                icon: 'fas fa-search'
            },
            {
                name: 'ML Analysis',
                description: 'Machine learning risk assessment',
                icon: 'fas fa-brain'
            },
            {
                name: 'Case Generation',
                description: 'Creating security cases',
                icon: 'fas fa-folder-open'
            },
            {
                name: 'Final Validation',
                description: 'Validating and finalizing results',
                icon: 'fas fa-check-circle'
            }
        ];
    }

    /**
     * Get professional stage card CSS class
     */
    getStageClass(status, isActive) {
        const baseClass = 'stage-card';
        
        if (status === 'error') return `${baseClass} stage-error`;
        if (status === 'complete') return `${baseClass} stage-complete`;
        if (status === 'processing' || isActive) return `${baseClass} stage-processing`;
        return `${baseClass} stage-waiting`;
    }

    /**
     * Get stage icon with status styling
     */
    getStageIcon(definition, status) {
        const baseIcon = definition.icon;
        
        if (status === 'error') {
            return `<i class="fas fa-exclamation-triangle text-danger"></i>`;
        } else if (status === 'complete') {
            return `<i class="fas fa-check-circle text-success"></i>`;
        } else if (status === 'processing') {
            return `<i class="fas fa-spinner fa-spin text-warning"></i>`;
        } else {
            return `<i class="${baseIcon} text-muted"></i>`;
        }
    }

    /**
     * Get stage status content with professional styling
     */
    getStageStatusContent(stage, status) {
        if (stage.error_message) {
            return `<i class="fas fa-exclamation-triangle"></i> Error: ${stage.error_message}`;
        }

        const statusContent = {
            'waiting': '<i class="fas fa-clock"></i> Waiting to start',
            'processing': '<i class="fas fa-spinner fa-spin"></i> Processing...',
            'complete': '<i class="fas fa-check"></i> Completed successfully',
            'error': '<i class="fas fa-times"></i> Processing failed'
        };

        return statusContent[status] || '<i class="fas fa-question"></i> Unknown status';
    }

    /**
     * Get status CSS class for badges
     */
    getStatusClass(status) {
        const statusClasses = {
            'uploaded': 'bg-secondary',
            'processing': 'bg-warning text-dark',
            'completed': 'bg-success',
            'error': 'bg-danger'
        };
        return statusClasses[status] || 'bg-secondary';
    }

    /**
     * Get status display text
     */
    getStatusText(status) {
        const statusTexts = {
            'uploaded': 'Uploaded',
            'processing': 'Processing',
            'completed': 'Completed',
            'error': 'Error'
        };
        return statusTexts[status] || 'Initializing';
    }

    /**
     * Get status icon
     */
    getStatusIcon(status) {
        const statusIcons = {
            'uploaded': 'fas fa-cloud-upload-alt',
            'processing': 'fas fa-spinner fa-spin',
            'completed': 'fas fa-check-circle',
            'error': 'fas fa-exclamation-triangle'
        };
        return statusIcons[status] || 'fas fa-circle';
    }

    /**
     * Animate progress bar with smooth transitions
     */
    animateProgressBar(progressBar, targetProgress) {
        const currentProgress = parseInt(progressBar.getAttribute('aria-valuenow') || '0');
        
        if (currentProgress !== targetProgress) {
            progressBar.style.width = `${targetProgress}%`;
            progressBar.setAttribute('aria-valuenow', targetProgress);
            
            // Add color transition based on progress
            const colorClass = this.getProgressBarClass(targetProgress);
            progressBar.className = `progress-bar ${colorClass}`;
        }
    }

    /**
     * Animate counter with smooth transitions
     */
    animateCounter(element, targetValue, suffix = '') {
        const currentValue = parseInt(element.textContent) || 0;
        const increment = targetValue > currentValue ? 1 : -1;
        const duration = Math.abs(targetValue - currentValue) * 20;
        
        let current = currentValue;
        const timer = setInterval(() => {
            current += increment;
            element.textContent = current + suffix;
            
            if ((increment > 0 && current >= targetValue) || 
                (increment < 0 && current <= targetValue)) {
                clearInterval(timer);
                element.textContent = targetValue + suffix;
            }
        }, Math.max(duration / Math.abs(targetValue - currentValue), 10));
    }

    /**
     * Add stagger animation to stage cards
     */
    addStaggerAnimation() {
        const cards = document.querySelectorAll('.stage-card');
        cards.forEach((card, index) => {
            card.style.animationDelay = `${index * 0.1}s`;
        });
    }

    /**
     * Get progress bar color class
     */
    getProgressBarClass(progress) {
        if (progress >= 100) return 'bg-success';
        if (progress >= 75) return 'bg-info';
        if (progress >= 50) return 'bg-warning';
        if (progress >= 25) return 'bg-primary';
        return 'bg-secondary';
    }

    /**
     * Format time remaining
     */
    formatTimeRemaining(seconds) {
        if (seconds < 60) return `${seconds}s remaining`;
        if (seconds < 3600) return `${Math.ceil(seconds / 60)}m remaining`;
        return `${Math.ceil(seconds / 3600)}h remaining`;
    }

    /**
     * Handle workflow completion
     */
    handleWorkflowComplete(data) {
        this.stopPolling();
        
        // Add completion animation
        const workflowSection = document.querySelector('.workflow-progress-section');
        if (workflowSection) {
            workflowSection.style.border = '2px solid #28a745';
            workflowSection.style.boxShadow = '0 4px 20px rgba(40, 167, 69, 0.2)';
        }
        
        // Show completion message
        setTimeout(() => {
            const completionAlert = document.getElementById('processingComplete');
            if (completionAlert) {
                completionAlert.style.display = 'block';
                completionAlert.scrollIntoView({ behavior: 'smooth' });
            }
        }, 1000);
    }

    /**
     * Handle workflow errors
     */
    handleWorkflowError(errorMessage) {
        const statusElement = document.getElementById('workflowStatus');
        if (statusElement) {
            statusElement.className = 'workflow-status-badge bg-danger';
            statusElement.innerHTML = `<i class="fas fa-exclamation-triangle"></i> Error`;
        }
        
        console.error('Workflow error:', errorMessage);
    }

    /**
     * Start enhanced polling with exponential backoff
     */
    startPolling() {
        if (this.isPolling) return;
        
        this.isPolling = true;
        let pollInterval = 2000; // Start with 2 seconds
        
        const poll = () => {
            this.loadWorkflowStatus().then(() => {
                if (this.isPolling) {
                    this.updateInterval = setTimeout(poll, pollInterval);
                }
            }).catch(() => {
                // Exponential backoff on errors
                pollInterval = Math.min(pollInterval * 1.5, 10000);
                if (this.isPolling) {
                    this.updateInterval = setTimeout(poll, pollInterval);
                }
            });
        };
        
        poll();
    }

    /**
     * Stop polling with cleanup
     */
    stopPolling() {
        if (this.updateInterval) {
            clearTimeout(this.updateInterval);
            this.updateInterval = null;
        }
        this.isPolling = false;
    }

    /**
     * Enhanced cleanup
     */
    cleanup() {
        this.stopPolling();
        this.animationQueue = [];
    }
}

// Global workflow manager instance
window.WorkflowManager = WorkflowManager;

// Enhanced auto-cleanup
window.addEventListener('beforeunload', () => {
    if (window.currentWorkflowManager) {
        window.currentWorkflowManager.cleanup();
    }
});

// Page visibility handling for performance
document.addEventListener('visibilitychange', () => {
    if (window.currentWorkflowManager) {
        if (document.hidden) {
            window.currentWorkflowManager.stopPolling();
        } else {
            window.currentWorkflowManager.startPolling();
        }
    }
});
