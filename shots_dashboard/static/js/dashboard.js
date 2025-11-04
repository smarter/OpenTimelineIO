// Dashboard JavaScript

class ShotsDashboard {
    constructor() {
        this.autoRefreshInterval = null;
        this.setupEventListeners();
        this.loadData();
        this.startAutoRefresh();
    }

    setupEventListeners() {
        document.getElementById('scan-btn').addEventListener('click', () => this.scanDirectory());
        document.getElementById('update-btn').addEventListener('click', () => this.updateTimeline());
        document.getElementById('reset-btn').addEventListener('click', () => this.reset());

        // Allow Enter key in inputs
        document.getElementById('scan-directory').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.scanDirectory();
        });
        document.getElementById('timeline-path').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.updateTimeline();
        });
    }

    async loadData() {
        try {
            this.showStatus('Loading...', 'info');

            const [statusRes, filesRes] = await Promise.all([
                fetch('/api/status'),
                fetch('/api/files')
            ]);

            const status = await statusRes.json();
            const files = await filesRes.json();

            if (status.success && files.success) {
                this.updateStats(status.stats);
                this.updateFiles(files.files);
                this.showStatus('Ready', 'success');
            } else {
                throw new Error(status.error || files.error);
            }
        } catch (error) {
            this.showStatus(`Error: ${error.message}`, 'error');
        }
    }

    async scanDirectory() {
        const directory = document.getElementById('scan-directory').value.trim();
        if (!directory) {
            this.showStatus('Please enter a directory path', 'error');
            return;
        }

        try {
            this.showStatus('Scanning directory...', 'info');
            this.disableButtons();

            const response = await fetch('/api/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ directory })
            });

            const result = await response.json();

            if (result.success) {
                this.showStatus(result.message, 'success');
                this.updateStats(result.stats);
                this.showTransitions(result.transitions);
                await this.loadData();
            } else {
                throw new Error(result.error);
            }
        } catch (error) {
            this.showStatus(`Error: ${error.message}`, 'error');
        } finally {
            this.enableButtons();
        }
    }

    async updateTimeline() {
        const timelinePath = document.getElementById('timeline-path').value.trim();
        if (!timelinePath) {
            this.showStatus('Please enter a timeline path', 'error');
            return;
        }

        try {
            this.showStatus('Updating from timeline...', 'info');
            this.disableButtons();

            const response = await fetch('/api/update_timeline', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ timeline_path: timelinePath })
            });

            const result = await response.json();

            if (result.success) {
                this.showStatus(result.message, 'success');
                this.updateStats(result.stats);
                this.showTransitions(result.transitions);
                await this.loadData();
            } else {
                throw new Error(result.error);
            }
        } catch (error) {
            this.showStatus(`Error: ${error.message}`, 'error');
        } finally {
            this.enableButtons();
        }
    }

    async reset() {
        if (!confirm('Are you sure you want to reset all state? This cannot be undone.')) {
            return;
        }

        try {
            this.showStatus('Resetting...', 'info');
            this.disableButtons();

            const response = await fetch('/api/reset', {
                method: 'POST'
            });

            const result = await response.json();

            if (result.success) {
                this.showStatus(result.message, 'success');
                await this.loadData();
                document.getElementById('transitions-list').innerHTML = '';
            } else {
                throw new Error(result.error);
            }
        } catch (error) {
            this.showStatus(`Error: ${error.message}`, 'error');
        } finally {
            this.enableButtons();
        }
    }

    updateStats(stats) {
        document.getElementById('stat-total').textContent = stats.total;
        document.getElementById('stat-new').textContent = stats.new;
        document.getElementById('stat-in-use').textContent = stats.in_use;
        document.getElementById('stat-removed').textContent = stats.removed;
    }

    updateFiles(files) {
        this.renderFileList('files-new', files.new, 'count-new');
        this.renderFileList('files-in-use', files.in_use, 'count-in-use');
        this.renderFileList('files-removed', files.removed, 'count-removed');
    }

    renderFileList(containerId, files, countId) {
        const container = document.getElementById(containerId);
        const countEl = document.getElementById(countId);

        countEl.textContent = files.length;

        if (files.length === 0) {
            container.innerHTML = '<div class="empty-state">No files</div>';
            return;
        }

        container.innerHTML = files.map(file => `
            <div class="file-item">
                <div class="file-name">${this.escapeHtml(file.name)}</div>
                <div class="file-path">${this.escapeHtml(file.path)}</div>
                <div class="file-time">${this.formatTime(file.last_updated)}</div>
            </div>
        `).join('');
    }

    showTransitions(transitions) {
        const container = document.getElementById('transitions-list');

        if (!transitions || transitions.length === 0) {
            return;
        }

        const html = transitions.map(t => {
            const oldState = t.old_state || 'none';
            return `
                <div class="transition-item">
                    <div class="transition-text">
                        <strong>${this.escapeHtml(t.name)}</strong>
                        <span class="transition-arrow">→</span>
                        <span class="state-badge state-${t.new_state}">${t.new_state}</span>
                    </div>
                    <div class="transition-time">${this.formatTime(t.timestamp)}</div>
                </div>
            `;
        }).join('');

        container.innerHTML = html + container.innerHTML;

        // Keep only last 20 transitions
        const items = container.querySelectorAll('.transition-item');
        if (items.length > 20) {
            for (let i = 20; i < items.length; i++) {
                items[i].remove();
            }
        }
    }

    showStatus(message, type) {
        const statusBar = document.getElementById('status-bar');
        const statusText = document.getElementById('status-text');

        statusText.textContent = message;
        statusBar.className = 'status-bar';

        if (type === 'success') {
            statusBar.classList.add('success');
        } else if (type === 'error') {
            statusBar.classList.add('error');
        }
    }

    disableButtons() {
        document.querySelectorAll('.btn').forEach(btn => {
            btn.disabled = true;
        });
    }

    enableButtons() {
        document.querySelectorAll('.btn').forEach(btn => {
            btn.disabled = false;
        });
    }

    formatTime(isoString) {
        const date = new Date(isoString);
        const now = new Date();
        const diff = now - date;

        // Less than 1 minute
        if (diff < 60000) {
            return 'just now';
        }
        // Less than 1 hour
        if (diff < 3600000) {
            const mins = Math.floor(diff / 60000);
            return `${mins} minute${mins > 1 ? 's' : ''} ago`;
        }
        // Less than 1 day
        if (diff < 86400000) {
            const hours = Math.floor(diff / 3600000);
            return `${hours} hour${hours > 1 ? 's' : ''} ago`;
        }
        // Show date
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    startAutoRefresh() {
        // Refresh every 2 seconds
        this.autoRefreshInterval = setInterval(() => {
            this.loadData();
        }, 2000);
    }

    stopAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }
    }
}

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', () => {
    new ShotsDashboard();
});
