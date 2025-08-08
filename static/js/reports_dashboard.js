/**
 * Professional Reports Dashboard JavaScript
 * Handles interactive charts, case selection, filtering, and bulk operations
 */

// Global variables
let allCases = [];
let filteredCases = [];
let groupedCases = [];
let selectedCases = new Set();
let charts = {};
let sessionId = '';
let currentViewMode = 'individual';

// Initialize dashboard
function initializeReportsDashboard() {
    // Get session ID from URL
    sessionId = window.location.pathname.split('/')[2];
    
    // Initialize all components
    loadCasesData();
    initializeEventListeners();
    updateSelection();
    initializeViewModeToggle();
}

// Load cases data from API
function loadCasesData() {
    fetch(`/api/cases/${sessionId}`)
        .then(response => response.json())
        .then(data => {
            allCases = data.cases || [];
            filteredCases = [...allCases];
            
            // Initialize charts with API data
            createStatusChart(data.status_distribution);
            createRiskChart(data.risk_distribution);
            createTimelineChart(data.timeline_data);
            createDomainsChart(data.top_domains);
            
            // Initialize counters
            initializeCounters(data);
        })
        .catch(error => {
            console.error('Error loading cases data:', error);
            showNotification('Error loading dashboard data', 'error');
        });
}

// Load grouped cases data from API
function loadGroupedCasesData() {
    fetch(`/api/grouped-cases/${sessionId}`)
        .then(response => response.json())
        .then(data => {
            groupedCases = data.grouped_cases || [];
            renderGroupedCases();
        })
        .catch(error => {
            console.error('Error loading grouped cases data:', error);
            showNotification('Error loading grouped cases data', 'error');
        });
}

// Initialize view mode toggle
function initializeViewModeToggle() {
    const individualViewRadio = document.getElementById('individualView');
    const groupedViewRadio = document.getElementById('groupedView');
    
    individualViewRadio.addEventListener('change', function() {
        if (this.checked) {
            currentViewMode = 'individual';
            switchToIndividualView();
        }
    });
    
    groupedViewRadio.addEventListener('change', function() {
        if (this.checked) {
            currentViewMode = 'grouped';
            switchToGroupedView();
        }
    });
}

// Switch to individual view
function switchToIndividualView() {
    document.getElementById('individualHeader').style.display = '';
    document.getElementById('groupedHeader').style.display = 'none';
    
    // Render individual cases (existing functionality)
    const tbody = document.getElementById('casesTableBody');
    tbody.innerHTML = '';
    
    // Re-render individual cases from server-side data
    // The table already contains server-rendered individual cases
    location.reload(); // Simple approach - reload to get individual view
}

// Switch to grouped view
function switchToGroupedView() {
    document.getElementById('individualHeader').style.display = 'none';
    document.getElementById('groupedHeader').style.display = '';
    
    // Load and render grouped cases
    loadGroupedCasesData();
}

// Render grouped cases
function renderGroupedCases() {
    const tbody = document.getElementById('casesTableBody');
    tbody.innerHTML = '';
    
    if (!groupedCases || groupedCases.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">No grouped cases found</td></tr>';
        return;
    }
    
    groupedCases.forEach((group, index) => {
        // Create main group row
        const groupRow = createGroupRowForReports(group, index);
        tbody.appendChild(groupRow);
        
        // Create expandable details row (initially hidden)
        const detailsRow = createGroupDetailsRowForReports(group, index);
        tbody.appendChild(detailsRow);
    });
}

// Create group row for reports dashboard
function createGroupRowForReports(group, index) {
    const row = document.createElement('tr');
    row.className = 'group-row';
    row.style.cursor = 'pointer';
    row.onclick = () => toggleGroupDetailsReports(index);
    
    // Get risk level badge class
    const riskBadgeClass = {
        'Critical': 'bg-danger',
        'High': 'bg-warning text-dark', 
        'Medium': 'bg-info',
        'Low': 'bg-success'
    }[group.risk_level] || 'bg-secondary';
    
    // Get status badge class
    const statusBadgeClass = {
        'Escalated': 'bg-danger',
        'Active': 'bg-primary',
        'Cleared': 'bg-success',
        'Mixed': 'bg-warning text-dark'
    }[group.group_status] || 'bg-secondary';
    
    row.innerHTML = `
        <td>
            <i class="fas fa-chevron-right group-toggle" id="toggle-${index}"></i>
        </td>
        <td>
            <div class="d-flex align-items-center">
                <div class="avatar-sm me-2">
                    <div class="avatar-title bg-primary rounded-circle">
                        ${(group.sender && group.sender[0]) ? group.sender[0].toUpperCase() : 'U'}
                    </div>
                </div>
                <div>
                    <div class="fw-bold">${group.sender || 'Unknown'}</div>
                    ${group.is_leaver ? '<span class="badge bg-warning text-dark">Leaver</span>' : ''}
                </div>
            </div>
        </td>
        <td>
            <span class="fw-bold">${(group.subject || 'No Subject').substring(0, 30)}${(group.subject || '').length > 30 ? '...' : ''}</span>
        </td>
        <td>
            <span class="badge bg-info">${group.record_count} recipient${group.record_count > 1 ? 's' : ''}</span>
        </td>
        <td>
            <span class="badge ${riskBadgeClass}">${group.risk_level}</span>
        </td>
        <td>
            <small>${group.time_display}</small>
        </td>
        <td>
            <span class="badge ${statusBadgeClass}">${group.group_status}</span>
        </td>
        <td>
            ${group.attachments ? '<i class="fas fa-paperclip text-warning"></i>' : '<span class="text-muted">None</span>'}
        </td>
        <td>
            <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-primary btn-sm" onclick="expandGroup(${index})" title="Expand Group">
                    <i class="fas fa-expand"></i>
                </button>
            </div>
        </td>
    `;
    
    return row;
}

// Create group details row for reports dashboard
function createGroupDetailsRowForReports(group, index) {
    const row = document.createElement('tr');
    row.className = 'group-details-row';
    row.id = `details-${index}`;
    row.style.display = 'none';
    
    const recipientsList = group.recipients.map(recipient => {
        const statusBadge = {
            'Active': 'bg-primary',
            'Cleared': 'bg-success', 
            'Escalated': 'bg-danger'
        }[recipient.case_status] || 'bg-secondary';
        
        const riskBadge = {
            'High': 'bg-danger',
            'Medium': 'bg-warning',
            'Low': 'bg-success'
        }[recipient.risk_level] || 'bg-secondary';
        
        return `
            <div class="recipient-item p-2 mb-2 border rounded">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <strong>${recipient.recipient || 'Unknown'}</strong>
                        <span class="badge bg-light text-dark ms-2">${recipient.recipient_domain || ''}</span>
                    </div>
                    <div>
                        <span class="badge ${riskBadge} me-1">${recipient.risk_level}</span>
                        <span class="badge ${statusBadge}">${recipient.case_status}</span>
                    </div>
                </div>
                ${recipient.notes ? `<div class="text-muted small mt-1">${recipient.notes}</div>` : ''}
            </div>
        `;
    }).join('');
    
    row.innerHTML = `
        <td colspan="9">
            <div class="p-3 bg-light border-start border-primary border-3">
                <h6><i class="fas fa-users"></i> Recipients (${group.recipients.length})</h6>
                <div class="recipients-container">
                    ${recipientsList}
                </div>
            </div>
        </td>
    `;
    
    return row;
}

// Toggle group details for reports dashboard
function toggleGroupDetailsReports(index) {
    const detailsRow = document.getElementById(`details-${index}`);
    const toggle = document.getElementById(`toggle-${index}`);
    
    if (detailsRow.style.display === 'none') {
        detailsRow.style.display = '';
        toggle.className = 'fas fa-chevron-down group-toggle';
    } else {
        detailsRow.style.display = 'none';
        toggle.className = 'fas fa-chevron-right group-toggle';
    }
}

// Expand group (same as toggle for now)
function expandGroup(index) {
    toggleGroupDetailsReports(index);
}
}

// Initialize event listeners
function initializeEventListeners() {
    // Filter inputs
    document.getElementById('statusFilter').addEventListener('change', applyFilters);
    document.getElementById('riskFilter').addEventListener('change', applyFilters);
    document.getElementById('dateFilter').addEventListener('change', applyFilters);
    document.getElementById('searchFilter').addEventListener('keyup', debounce(applyFilters, 300));
    
    // Case checkboxes
    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('case-checkbox')) {
            updateCaseSelection(e.target);
        }
    });
    
    // Select all checkbox
    document.getElementById('selectAllCheckbox').addEventListener('change', toggleSelectAll);
}

// Create status distribution chart
function createStatusChart(data) {
    const ctx = document.getElementById('statusChart').getContext('2d');
    
    // Destroy existing chart if it exists
    if (charts.status) {
        charts.status.destroy();
    }
    
    charts.status = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: Object.keys(data),
            datasets: [{
                data: Object.values(data),
                backgroundColor: [
                    '#4e73df', // Active - Blue
                    '#1cc88a', // Cleared - Green
                    '#e74a3b'  // Escalated - Red
                ],
                hoverBackgroundColor: [
                    '#2e59d9',
                    '#17a673',
                    '#e02d1b'
                ],
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            maintainAspectRatio: false,
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 20,
                        usePointStyle: true
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((context.raw / total) * 100).toFixed(1);
                            return `${context.label}: ${context.raw} (${percentage}%)`;
                        }
                    }
                }
            },
            animation: {
                animateRotate: true,
                duration: 1000
            }
        }
    });
}

// Create risk level chart
function createRiskChart(data) {
    const ctx = document.getElementById('riskChart').getContext('2d');
    
    if (charts.risk) {
        charts.risk.destroy();
    }
    
    charts.risk = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: Object.keys(data),
            datasets: [{
                label: 'Cases',
                data: Object.values(data),
                backgroundColor: [
                    '#e74a3b', // High - Red
                    '#f6c23e', // Medium - Yellow
                    '#1cc88a'  // Low - Green
                ],
                borderColor: [
                    '#e74a3b',
                    '#f6c23e',
                    '#1cc88a'
                ],
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            maintainAspectRatio: false,
            responsive: true,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            return `${context[0].label} Risk Level`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            },
            animation: {
                duration: 1000,
                easing: 'easeInOutQuart'
            }
        }
    });
}

// Create timeline chart
function createTimelineChart(data) {
    const ctx = document.getElementById('timelineChart').getContext('2d');
    
    if (charts.timeline) {
        charts.timeline.destroy();
    }
    
    charts.timeline = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Cases Over Time',
                data: data.data,
                borderColor: '#4e73df',
                backgroundColor: 'rgba(78, 115, 223, 0.1)',
                fill: true,
                tension: 0.3,
                pointBackgroundColor: '#4e73df',
                pointBorderColor: '#ffffff',
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            maintainAspectRatio: false,
            responsive: true,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            },
            animation: {
                duration: 1500,
                easing: 'easeInOutCubic'
            }
        }
    });
}

// Create domains chart
function createDomainsChart(data) {
    const ctx = document.getElementById('domainsChart').getContext('2d');
    
    if (charts.domains) {
        charts.domains.destroy();
    }
    
    charts.domains = new Chart(ctx, {
        type: 'horizontalBar',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Cases',
                data: data.data,
                backgroundColor: '#36b9cc',
                borderColor: '#36b9cc',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            maintainAspectRatio: false,
            responsive: true,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                },
                y: {
                    grid: {
                        display: false
                    }
                }
            },
            animation: {
                duration: 1000,
                easing: 'easeInOutQuart'
            }
        }
    });
}

// Initialize animated counters
function initializeCounters(data) {
    const counters = [
        { id: 'totalCasesCounter', value: data.cases.length },
        { id: 'highRiskCounter', value: data.cases.filter(c => c.risk_level === 'High').length },
        { id: 'resolvedCounter', value: data.cases.filter(c => ['Cleared', 'Escalated'].includes(c.status)).length },
        { id: 'pendingCounter', value: data.cases.filter(c => c.status === 'Active').length }
    ];
    
    counters.forEach(counter => {
        animateCounter(counter.id, counter.value);
    });
}

// Animate counter with easing
function animateCounter(elementId, targetValue, duration = 1000) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    let startValue = 0;
    const startTime = performance.now();
    
    function updateCounter(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        
        // Easing function (ease-out)
        const easeOut = 1 - Math.pow(1 - progress, 3);
        const currentValue = Math.floor(startValue + (targetValue - startValue) * easeOut);
        
        element.textContent = currentValue.toLocaleString();
        
        if (progress < 1) {
            requestAnimationFrame(updateCounter);
        } else {
            element.textContent = targetValue.toLocaleString();
        }
    }
    
    requestAnimationFrame(updateCounter);
}

// Apply filters to cases
function applyFilters() {
    const statusFilter = document.getElementById('statusFilter').value;
    const riskFilter = document.getElementById('riskFilter').value;
    const dateFilter = document.getElementById('dateFilter').value;
    const searchFilter = document.getElementById('searchFilter').value.toLowerCase();

    filteredCases = allCases.filter(caseItem => {
        // Status filter
        if (statusFilter && caseItem.status !== statusFilter) return false;
        
        // Risk filter
        if (riskFilter && caseItem.risk_level !== riskFilter) return false;
        
        // Date filter
        if (dateFilter) {
            const caseDate = new Date(caseItem.time).toISOString().split('T')[0];
            if (caseDate !== dateFilter) return false;
        }
        
        // Search filter
        if (searchFilter) {
            const searchableText = [
                caseItem.sender_email,
                caseItem.subject,
                caseItem.recipient_domain
            ].join(' ').toLowerCase();
            
            if (!searchableText.includes(searchFilter)) return false;
        }
        
        return true;
    });

    updateCasesTable();
    updateFilteredCounters();
}

// Update cases table based on filtered results
function updateCasesTable() {
    const tbody = document.getElementById('casesTableBody');
    if (!tbody) return;
    
    // Clear existing rows
    tbody.innerHTML = '';
    
    // Add filtered cases
    filteredCases.forEach(caseItem => {
        const row = createCaseRow(caseItem);
        tbody.appendChild(row);
    });
    
    // Update selection state
    updateSelectionCheckboxes();
}

// Create a table row for a case
function createCaseRow(caseItem) {
    const row = document.createElement('tr');
    row.setAttribute('data-case-id', caseItem.record_id);
    row.setAttribute('data-risk', caseItem.risk_level);
    row.setAttribute('data-status', caseItem.status);
    
    row.innerHTML = `
        <td>
            <input type="checkbox" class="case-checkbox" value="${caseItem.record_id}" onchange="updateSelection()">
        </td>
        <td>
            <div class="d-flex align-items-center">
                <div class="avatar-sm me-2">
                    <div class="avatar-title bg-primary rounded-circle">
                        ${caseItem.sender_email[0].toUpperCase()}
                    </div>
                </div>
                <div>
                    <div class="fw-bold">${truncateText(caseItem.sender_email, 20)}</div>
                </div>
            </div>
        </td>
        <td>
            <span class="fw-bold">${truncateText(caseItem.subject, 30)}</span>
        </td>
        <td>
            <span class="badge bg-light text-dark">${caseItem.recipient_domain}</span>
        </td>
        <td>
            ${createRiskBadge(caseItem.risk_level)}
        </td>
        <td>
            ${createMLScoreProgress(caseItem.ml_score)}
        </td>
        <td>
            ${createStatusBadge(caseItem.status)}
        </td>
        <td>
            <small>${formatDateTime(caseItem.time)}</small>
        </td>
        <td>
            ${caseItem.attachments ? 
                `<i class="fas fa-paperclip text-warning" title="Has attachments"></i>` : 
                '<span class="text-muted">None</span>'
            }
        </td>
        <td>
            <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-primary btn-sm" onclick="viewCaseDetails('${caseItem.record_id}')" title="View Details">
                    <i class="fas fa-eye"></i>
                </button>
                <button class="btn btn-outline-warning btn-sm" onclick="editCaseStatus('${caseItem.record_id}')" title="Edit Status">
                    <i class="fas fa-edit"></i>
                </button>
            </div>
        </td>
    `;
    
    return row;
}

// Helper functions for creating UI elements
function createRiskBadge(riskLevel) {
    const badgeClass = {
        'High': 'bg-danger',
        'Medium': 'bg-warning',
        'Low': 'bg-success'
    }[riskLevel] || 'bg-secondary';
    
    return `<span class="badge ${badgeClass}">${riskLevel} Risk</span>`;
}

function createMLScoreProgress(mlScore) {
    const percentage = (mlScore * 100).toFixed(1);
    const progressClass = mlScore >= 0.7 ? 'bg-danger' : mlScore >= 0.4 ? 'bg-warning' : 'bg-success';
    
    return `
        <div class="progress" style="height: 20px;">
            <div class="progress-bar ${progressClass}" 
                 role="progressbar" 
                 style="width: ${percentage}%">
                ${percentage}%
            </div>
        </div>
    `;
}

function createStatusBadge(status) {
    const badgeClass = {
        'Active': 'bg-primary',
        'Cleared': 'bg-success',
        'Escalated': 'bg-danger'
    }[status] || 'bg-secondary';
    
    return `<span class="badge ${badgeClass}">${status}</span>`;
}

function truncateText(text, maxLength) {
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
}

function formatDateTime(dateTimeString) {
    const date = new Date(dateTimeString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
}

// Selection management
function toggleSelectAll() {
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    const caseCheckboxes = document.querySelectorAll('.case-checkbox');
    
    selectedCases.clear();
    
    caseCheckboxes.forEach(checkbox => {
        checkbox.checked = selectAllCheckbox.checked;
        if (selectAllCheckbox.checked) {
            selectedCases.add(checkbox.value);
        }
    });
    
    updateSelection();
}

function updateCaseSelection(checkbox) {
    if (checkbox.checked) {
        selectedCases.add(checkbox.value);
    } else {
        selectedCases.delete(checkbox.value);
    }
    
    updateSelection();
}

function selectAllCases() {
    document.getElementById('selectAllCheckbox').checked = true;
    toggleSelectAll();
}

function clearSelection() {
    document.getElementById('selectAllCheckbox').checked = false;
    toggleSelectAll();
}

function updateSelection() {
    const count = selectedCases.size;
    const summaryDiv = document.getElementById('selectionSummary');
    const selectionText = document.getElementById('selectionText');
    const exportBtn = document.getElementById('exportBtn');
    const bulkUpdateBtn = document.getElementById('bulkUpdateBtn');
    
    // Update UI based on selection count
    if (count > 0) {
        summaryDiv.style.display = 'block';
        selectionText.textContent = `${count} case${count > 1 ? 's' : ''} selected`;
        exportBtn.disabled = false;
        bulkUpdateBtn.disabled = false;
        
        // Calculate breakdown
        updateSelectionBreakdown();
    } else {
        summaryDiv.style.display = 'none';
        exportBtn.disabled = true;
        bulkUpdateBtn.disabled = true;
    }
    
    // Update select all checkbox state
    updateSelectAllCheckboxState();
}

function updateSelectionBreakdown() {
    let breakdown = { high: 0, medium: 0, low: 0, active: 0, cleared: 0, escalated: 0 };
    
    selectedCases.forEach(caseId => {
        const row = document.querySelector(`tr[data-case-id="${caseId}"]`);
        if (row) {
            const risk = row.dataset.risk;
            const status = row.dataset.status;
            
            if (risk) breakdown[risk.toLowerCase()]++;
            if (status) breakdown[status.toLowerCase()]++;
        }
    });
    
    const breakdownText = `High Risk: ${breakdown.high}, Medium: ${breakdown.medium}, Low: ${breakdown.low} | ` +
                         `Active: ${breakdown.active}, Cleared: ${breakdown.cleared}, Escalated: ${breakdown.escalated}`;
    
    document.getElementById('selectionBreakdown').textContent = breakdownText;
}

function updateSelectAllCheckboxState() {
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    const caseCheckboxes = document.querySelectorAll('.case-checkbox');
    const checkedCount = document.querySelectorAll('.case-checkbox:checked').length;
    
    if (checkedCount === 0) {
        selectAllCheckbox.indeterminate = false;
        selectAllCheckbox.checked = false;
    } else if (checkedCount === caseCheckboxes.length) {
        selectAllCheckbox.indeterminate = false;
        selectAllCheckbox.checked = true;
    } else {
        selectAllCheckbox.indeterminate = true;
        selectAllCheckbox.checked = false;
    }
}

function updateSelectionCheckboxes() {
    document.querySelectorAll('.case-checkbox').forEach(checkbox => {
        checkbox.checked = selectedCases.has(checkbox.value);
    });
    updateSelectAllCheckboxState();
}

// Case actions
function viewCaseDetails(caseId) {
    const caseData = allCases.find(c => c.record_id === caseId);
    if (!caseData) return;
    
    // Create and show modal with case details
    showCaseDetailsModal(caseData);
}

function editCaseStatus(caseId) {
    // Implementation for editing individual case status
    const newStatus = prompt('Enter new status (Active, Cleared, Escalated):');
    if (newStatus && ['Active', 'Cleared', 'Escalated'].includes(newStatus)) {
        updateCaseStatus(caseId, newStatus);
    }
}

function updateCaseStatus(caseId, newStatus) {
    fetch(`/api/bulk-update-status/${sessionId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            case_ids: [caseId],
            new_status: newStatus
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification(`Case status updated to ${newStatus}`, 'success');
            // Reload the page to refresh data
            setTimeout(() => location.reload(), 1000);
        } else {
            showNotification('Error updating case status', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification('Error updating case status', 'error');
    });
}

// Export functions
function exportSelectedCases() {
    if (selectedCases.size === 0) {
        showNotification('Please select cases to export', 'warning');
        return;
    }
    
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = `/api/export-cases/${sessionId}`;
    
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'case_ids';
    input.value = JSON.stringify([...selectedCases]);
    
    form.appendChild(input);
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
    
    showNotification('Export started', 'info');
}

function generateFullReport() {
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = `/api/generate-report/${sessionId}`;
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
    
    showNotification('Report generation started', 'info');
}

// Bulk update functions
function bulkUpdateStatus() {
    if (selectedCases.size === 0) {
        showNotification('Please select cases to update', 'warning');
        return;
    }
    
    document.getElementById('bulkUpdateCount').textContent = selectedCases.size;
    const modal = new bootstrap.Modal(document.getElementById('bulkUpdateModal'));
    modal.show();
}

function confirmBulkUpdate() {
    const newStatus = document.getElementById('newStatus').value;
    if (!newStatus) {
        showNotification('Please select a status', 'warning');
        return;
    }
    
    fetch(`/api/bulk-update-status/${sessionId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            case_ids: [...selectedCases],
            new_status: newStatus
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification(`Successfully updated ${data.updated_count} cases`, 'success');
            // Close modal and reload page
            bootstrap.Modal.getInstance(document.getElementById('bulkUpdateModal')).hide();
            setTimeout(() => location.reload(), 1000);
        } else {
            showNotification('Error updating cases: ' + data.error, 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification('Error updating cases', 'error');
    });
}

// Utility functions
function refreshDashboard() {
    location.reload();
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

function showCaseDetailsModal(caseData) {
    // Create modal content with case details
    const modalHtml = `
        <div class="modal fade" id="caseDetailsModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Case Details - ${caseData.record_id}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="row">
                            <div class="col-md-6">
                                <strong>Sender:</strong> ${caseData.sender_email}<br>
                                <strong>Subject:</strong> ${caseData.subject}<br>
                                <strong>Domain:</strong> ${caseData.recipient_domain}<br>
                                <strong>Risk Level:</strong> ${createRiskBadge(caseData.risk_level)}<br>
                            </div>
                            <div class="col-md-6">
                                <strong>ML Score:</strong> ${(caseData.ml_score * 100).toFixed(1)}%<br>
                                <strong>Status:</strong> ${createStatusBadge(caseData.status)}<br>
                                <strong>Time:</strong> ${formatDateTime(caseData.time)}<br>
                                <strong>Attachments:</strong> ${caseData.attachments || 'None'}<br>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        <button type="button" class="btn btn-primary" onclick="editCaseStatus('${caseData.record_id}')">Edit Status</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal if present
    const existingModal = document.getElementById('caseDetailsModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add modal to page and show
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const modal = new bootstrap.Modal(document.getElementById('caseDetailsModal'));
    modal.show();
    
    // Clean up modal after hiding
    document.getElementById('caseDetailsModal').addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
}

// Debounce function for search input
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function updateFilteredCounters() {
    // Update counters based on filtered results
    const filteredCounters = {
        total: filteredCases.length,
        highRisk: filteredCases.filter(c => c.risk_level === 'High').length,
        resolved: filteredCases.filter(c => ['Cleared', 'Escalated'].includes(c.status)).length,
        pending: filteredCases.filter(c => c.status === 'Active').length
    };
    
    // Update counter displays (optional - can show filtered vs total)
    // For now, we'll keep the original totals displayed
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeReportsDashboard);