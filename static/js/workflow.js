/**
 * Workflow Progress Management for Email Guardian
 * Handles the 8-stage processing workflow display and updates
 */

class WorkflowManager {
    constructor(sessionId) {
        this.sessionId = sessionId;
        this.updateInterval = null;
        this.isPolling = false;
    }

    /**
     * Initialize workflow display
     */
    initializeWorkflow() {
        const workflowContainer = document.getElementById('workflowContainer');
        if (!workflowContainer) {
            console.warn('Workflow container not found');
            return;
        }

        const workflowHtml = `
            <div class="workflow-progress-section">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h5 class="mb-0">
                        <i class="fas fa-cogs text-primary"></i> Processing Workflow
                    </h5>
                    <div class="workflow-controls">
                        <span id="workflowStatus" class="badge bg-secondary">Initializing</span>
                        <span id="overallProgress" class="badge bg-info ms-2">0%</span>
                    </div>
                </div>
                
                <!-- Overall Progress Bar -->
                <div class="progress mb-4" style="height: 8px;">
                    <div id="overallProgressBar" class="progress-bar bg-gradient" 
                         role="progressbar" style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                    </div>
                </div>
                
                <!-- Workflow Stages -->
                <div class="workflow-stages row g-2" id="workflowStages">
                    <!-- Stages will be populated dynamically -->
                </div>
            </div>
        `;

        workflowContainer.innerHTML = workflowHtml;
        this.loadWorkflowStatus();
    }

    /**
     * Load current workflow status from API
     */
    async loadWorkflowStatus() {
        try {
            const response = await fetch(`/api/workflow/${this.sessionId}/status`);
            const data = await response.json();

            if (data.error) {
                console.error('Error loading workflow status:', data.error);
                return;
            }

            this.updateWorkflowDisplay(data);
            
            // Start polling if processing
            if (data.status === 'processing') {
                this.startPolling();
            }
        } catch (error) {
            console.error('Error fetching workflow status:', error);
        }
    }

    /**
     * Update workflow display with current status
     */
    updateWorkflowDisplay(workflowData) {
        const { current_stage, overall_progress, status, stages } = workflowData;

        // Update overall status and progress
        const statusElement = document.getElementById('workflowStatus');
        const progressElement = document.getElementById('overallProgress');
        const progressBar = document.getElementById('overallProgressBar');

        if (statusElement) {
            const statusClass = this.getStatusClass(status);
            statusElement.className = `badge ${statusClass}`;
            statusElement.textContent = this.getStatusText(status);
        }

        if (progressElement) {
            progressElement.textContent = `${Math.round(overall_progress)}%`;
        }

        if (progressBar) {
            progressBar.style.width = `${overall_progress}%`;
            progressBar.setAttribute('aria-valuenow', overall_progress);
            
            // Change color based on progress
            progressBar.className = `progress-bar ${this.getProgressBarClass(overall_progress)}`;
        }

        // Update individual stages
        this.updateStagesDisplay(stages, current_stage);
    }

    /**
     * Update individual stages display
     */
    updateStagesDisplay(stages, currentStage) {
        const stagesContainer = document.getElementById('workflowStages');
        if (!stagesContainer || !stages) return;

        let stagesHtml = '';

        for (let i = 1; i <= 8; i++) {
            const stage = stages[i.toString()];
            if (!stage) continue;

            const stageStatus = stage.status;
            const isActive = i === currentStage;
            const stageClass = this.getStageClass(stageStatus, isActive);
            const icon = this.getStageIcon(stage, stageStatus);

            stagesHtml += `
                <div class="col-md-3 col-sm-6 mb-3">
                    <div class="stage-card ${stageClass}" data-stage="${i}">
                        <div class="stage-header">
                            <div class="stage-icon">
                                ${icon}
                            </div>
                            <div class="stage-number">${i}</div>
                        </div>
                        <div class="stage-content">
                            <h6 class="stage-title">${stage.name}</h6>
                            <p class="stage-description">${stage.description}</p>
                            <div class="stage-progress">
                                <div class="progress" style="height: 4px;">
                                    <div class="progress-bar" style="width: ${stage.progress}%"></div>
                                </div>
                                <small class="text-muted">${stage.progress}%</small>
                            </div>
                            ${this.getStageStatus(stage, stageStatus)}
                        </div>
                    </div>
                </div>
            `;
        }

        stagesContainer.innerHTML = stagesHtml;
    }

    /**
     * Get stage card CSS class based on status
     */
    getStageClass(status, isActive) {
        const baseClass = 'card h-100 stage-card';
        
        if (status === 'error') return `${baseClass} border-danger`;
        if (status === 'complete') return `${baseClass} border-success`;
        if (status === 'processing' || isActive) return `${baseClass} border-warning shadow-sm`;
        return `${baseClass} border-light`;
    }

    /**
     * Get stage icon based on status
     */
    getStageIcon(stage, status) {
        const baseIcon = stage.icon || 'fas fa-circle';
        
        if (status === 'error') {
            return `<i class="${baseIcon} text-danger"></i>`;
        } else if (status === 'complete') {
            return `<i class="fas fa-check-circle text-success"></i>`;
        } else if (status === 'processing') {
            return `<i class="fas fa-spinner fa-spin text-warning"></i>`;
        } else {
            return `<i class="${baseIcon} text-muted"></i>`;
        }
    }

    /**
     * Get stage status text
     */
    getStageStatus(stage, status) {
        if (stage.error_message) {
            return `<small class="text-danger"><i class="fas fa-exclamation-triangle"></i> ${stage.error_message}</small>`;
        }

        const statusTexts = {
            'waiting': '<small class="text-muted"><i class="fas fa-clock"></i> Waiting</small>',
            'processing': '<small class="text-warning"><i class="fas fa-spinner fa-spin"></i> Processing</small>',
            'complete': '<small class="text-success"><i class="fas fa-check"></i> Complete</small>',
            'error': '<small class="text-danger"><i class="fas fa-times"></i> Error</small>'
        };

        return statusTexts[status] || '<small class="text-muted">Unknown</small>';
    }

    /**
     * Get status CSS class
     */
    getStatusClass(status) {
        const statusClasses = {
            'uploaded': 'bg-secondary',
            'processing': 'bg-warning',
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
        return statusTexts[status] || 'Unknown';
    }

    /**
     * Get progress bar class based on progress
     */
    getProgressBarClass(progress) {
        if (progress >= 100) return 'bg-success';
        if (progress >= 80) return 'bg-info';
        if (progress >= 50) return 'bg-warning';
        return 'bg-primary';
    }

    /**
     * Start polling for workflow updates
     */
    startPolling() {
        if (this.isPolling) return;
        
        this.isPolling = true;
        this.updateInterval = setInterval(() => {
            this.loadWorkflowStatus();
        }, 2000); // Poll every 2 seconds
    }

    /**
     * Stop polling for workflow updates
     */
    stopPolling() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
        this.isPolling = false;
    }

    /**
     * Cleanup when workflow is complete or page is unloaded
     */
    cleanup() {
        this.stopPolling();
    }
}

// Global workflow manager instance
window.WorkflowManager = WorkflowManager;

// Auto-cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.currentWorkflowManager) {
        window.currentWorkflowManager.cleanup();
    }
});