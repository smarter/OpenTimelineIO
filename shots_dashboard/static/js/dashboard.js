// Dashboard JavaScript

class ShotsDashboard {
    constructor() {
        this.socket = null;
        this.previewTimeout = null;
        this.currentPreviewFilename = null;
        this.setupEventListeners();
        this.setupVideoPreview();
        this.setupWebSocket();
        // Initial load will come from WebSocket connection
    }

    setupEventListeners() {
        document.getElementById('scan-btn').addEventListener('click', () => this.scanDirectory());
        document.getElementById('update-btn').addEventListener('click', () => this.updateTimeline());
        document.getElementById('reset-btn').addEventListener('click', () => this.reset());

        // Timeline history toggle
        document.getElementById('show-historical-toggle').addEventListener('change', (e) => {
            this.toggleHistoricalTimeline(e.target.checked);
        });

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

            const [statusRes, filesRes, timelineHistoryRes] = await Promise.all([
                fetch('/api/status'),
                fetch('/api/files'),
                fetch('/api/timeline_history')
            ]);

            const status = await statusRes.json();
            const files = await filesRes.json();
            const timelineHistory = await timelineHistoryRes.json();

            if (status.success && files.success && timelineHistory.success) {
                this.updateStats(status.stats);
                this.updateFiles(files.files);
                this.updateTimelineHistory(timelineHistory);
                this.showStatus('Ready', 'success');
            } else {
                throw new Error(status.error || files.error || timelineHistory.error);
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
        // Animate stat values when they change
        this.animateStatValue('stat-total', stats.total);
        this.animateStatValue('stat-new', stats.new);
        this.animateStatValue('stat-in-use', stats.in_use);
        this.animateStatValue('stat-removed', stats.removed);
    }

    animateStatValue(elementId, newValue) {
        const element = document.getElementById(elementId);
        const oldValue = parseInt(element.textContent) || 0;

        if (oldValue !== newValue) {
            // Add animation class
            element.classList.add('updated');

            // Animate number counting
            const duration = 500; // ms
            const steps = 20;
            const stepValue = (newValue - oldValue) / steps;
            const stepDuration = duration / steps;
            let currentStep = 0;

            const interval = setInterval(() => {
                currentStep++;
                if (currentStep >= steps) {
                    element.textContent = newValue;
                    clearInterval(interval);
                } else {
                    element.textContent = Math.round(oldValue + (stepValue * currentStep));
                }
            }, stepDuration);

            // Remove animation class after animation completes
            setTimeout(() => {
                element.classList.remove('updated');
            }, 600);

            // Pulse the stat card
            const card = element.closest('.stat-card');
            if (card) {
                card.classList.add('updated');
                setTimeout(() => card.classList.remove('updated'), 800);
            }
        } else {
            element.textContent = newValue;
        }
    }

    updateFiles(files) {
        this.renderFileList('files-new', files.new, 'count-new');
        this.renderFileList('files-in-use', files.in_use, 'count-in-use');
        this.renderFileList('files-removed', files.removed, 'count-removed');
    }

    renderFileList(containerId, files, countId) {
        const container = document.getElementById(containerId);
        const countEl = document.getElementById(countId);

        // Get existing file paths to detect new ones
        const existingPaths = new Set(
            Array.from(container.querySelectorAll('.file-item')).map(item =>
                item.querySelector('.file-path').textContent
            )
        );

        countEl.textContent = files.length;

        if (files.length === 0) {
            container.innerHTML = '<div class="empty-state">No files</div>';
            return;
        }

        container.innerHTML = files.map(file => {
            const isNew = !existingPaths.has(file.path);
            const newItemClass = isNew ? 'new-item' : '';
            return `
                <div class="file-item ${newItemClass}">
                    <div class="file-name" data-filename="${this.escapeHtml(file.name)}">${this.escapeHtml(file.name)}</div>
                    <div class="file-path">${this.escapeHtml(file.path)}</div>
                    <div class="file-time">${this.formatTime(file.last_updated)}</div>
                </div>
            `;
        }).join('');

        // Attach preview handlers to file names
        container.querySelectorAll('.file-name').forEach(el => {
            const filename = el.getAttribute('data-filename');
            if (filename) {
                this.attachPreviewHandlers(el, filename);
            }
        });

        // Flash the container to indicate update
        container.classList.add('updated');
        setTimeout(() => container.classList.remove('updated'), 800);
    }

    showTransitions(transitions) {
        const container = document.getElementById('transitions-list');

        if (!transitions || transitions.length === 0) {
            return;
        }

        const html = transitions.map(t => {
            const oldState = t.old_state || 'none';
            return `
                <div class="transition-item new-transition">
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

        // Remove animation class after animation completes
        setTimeout(() => {
            container.querySelectorAll('.transition-item').forEach(item => {
                item.classList.remove('new-transition');
            });
        }, 500);

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

    updateTimelineHistory(history) {
        const currentInfo = document.getElementById('timeline-current-info');
        const currentClips = document.getElementById('timeline-current-clips');
        const historicalClips = document.getElementById('timeline-historical-clips');
        const timelineWidget = document.getElementById('timeline-widget');

        // Get existing clips to detect new ones
        const existingCurrentClips = new Set(
            Array.from(currentClips.querySelectorAll('.clip-badge')).map(badge =>
                badge.getAttribute('data-filename')
            )
        );

        // Update current timeline
        if (history.current) {
            const path = history.current.timeline_path;
            const filename = path ? path.split('/').pop() : 'Unknown';
            const timestamp = history.current.timestamp ? this.formatTime(history.current.timestamp) : '';

            currentInfo.innerHTML = `
                <p><strong>${history.current.clips.length} clips</strong> in current timeline</p>
                <p class="timeline-path">${this.escapeHtml(filename)}</p>
                <p class="timeline-timestamp">Updated ${timestamp}</p>
            `;

            if (history.current.clips.length > 0) {
                currentClips.innerHTML = history.current.clips.map(clip => {
                    const isNewClip = !existingCurrentClips.has(clip);
                    const newClipClass = isNewClip ? 'new-clip' : '';
                    return `<span class="clip-badge ${newClipClass}" data-filename="${this.escapeHtml(clip)}">${this.escapeHtml(clip)}</span>`;
                }).join('');

                // Attach preview handlers
                currentClips.querySelectorAll('.clip-badge').forEach(el => {
                    const filename = el.getAttribute('data-filename');
                    if (filename) {
                        this.attachPreviewHandlers(el, filename);
                    }
                });

                // Remove animation class after animation completes
                setTimeout(() => {
                    currentClips.querySelectorAll('.clip-badge').forEach(badge => {
                        badge.classList.remove('new-clip');
                    });
                }, 400);
            } else {
                currentClips.innerHTML = '<p class="empty-state">No clips in timeline</p>';
            }

            // Animate the timeline widget
            timelineWidget.classList.add('updated');
            setTimeout(() => timelineWidget.classList.remove('updated'), 1000);
        } else {
            currentInfo.innerHTML = '<p class="empty-state">No timeline loaded yet</p>';
            currentClips.innerHTML = '';
        }

        // Update historical clips
        if (history.historical_clips && history.historical_clips.length > 0) {
            historicalClips.innerHTML = history.historical_clips.map(clip =>
                `<span class="clip-badge historical" data-filename="${this.escapeHtml(clip)}">${this.escapeHtml(clip)}</span>`
            ).join('');

            // Attach preview handlers
            historicalClips.querySelectorAll('.clip-badge').forEach(el => {
                const filename = el.getAttribute('data-filename');
                if (filename) {
                    this.attachPreviewHandlers(el, filename);
                }
            });
        } else {
            historicalClips.innerHTML = '<p class="empty-state">No historical clips</p>';
        }
    }

    toggleHistoricalTimeline(show) {
        const historicalSection = document.getElementById('timeline-historical');
        historicalSection.style.display = show ? 'block' : 'none';
    }

    setupWebSocket() {
        // Connect to WebSocket server
        this.socket = io();

        // Handle connection
        this.socket.on('connect', () => {
            console.log('WebSocket connected');
            this.showStatus('Connected', 'success');
        });

        // Handle disconnection
        this.socket.on('disconnect', () => {
            console.log('WebSocket disconnected');
            this.showStatus('Disconnected - Reconnecting...', 'error');
        });

        // Handle all state update events
        const updateEvents = [
            'initial_state',
            'state_update',
            'scan_complete',
            'timeline_update_complete',
            'reset_complete'
        ];

        updateEvents.forEach(event => {
            this.socket.on(event, (data) => {
                console.log(`Received ${event}:`, data);
                this.handleStateUpdate(data);
            });
        });

        // Handle errors
        this.socket.on('error', (data) => {
            console.error('WebSocket error:', data);
            this.showStatus(`Error: ${data.message}`, 'error');
        });
    }

    handleStateUpdate(data) {
        // Update UI with new state from WebSocket
        if (data.stats) {
            this.updateStats(data.stats);
        }

        if (data.files) {
            this.updateFiles(data.files);
        }

        if (data.timeline_history) {
            this.updateTimelineHistory(data.timeline_history);
        }

        this.showStatus('Ready', 'success');
    }

    setupVideoPreview() {
        this.previewPopup = document.getElementById('video-preview-popup');
        this.previewPlayer = document.getElementById('video-preview-player');
        this.previewSource = document.getElementById('video-preview-source');
        this.previewFilename = document.getElementById('video-preview-filename');
    }

    showVideoPreview(filename, element) {
        // Cancel any pending preview
        if (this.previewTimeout) {
            clearTimeout(this.previewTimeout);
        }

        // Delay showing preview to avoid flickering on quick mouse movements
        this.previewTimeout = setTimeout(() => {
            this.currentPreviewFilename = filename;

            // Show loading state
            this.previewPopup.classList.add('loading');
            this.previewFilename.textContent = filename;

            // Position popup near the element
            const rect = element.getBoundingClientRect();
            const popupWidth = 400;
            const popupHeight = 300;

            // Position to the right of element, or left if not enough space
            let left = rect.right + 10;
            if (left + popupWidth > window.innerWidth) {
                left = rect.left - popupWidth - 10;
            }

            // Position vertically centered with element
            let top = rect.top + (rect.height / 2) - (popupHeight / 2);

            // Keep within viewport
            top = Math.max(10, Math.min(top, window.innerHeight - popupHeight - 10));
            left = Math.max(10, Math.min(left, window.innerWidth - popupWidth - 10));

            this.previewPopup.style.left = left + 'px';
            this.previewPopup.style.top = top + 'px';
            this.previewPopup.style.display = 'block';

            // Load video
            this.previewSource.src = `/api/preview/${encodeURIComponent(filename)}`;
            this.previewPlayer.load();

            // Start playing when loaded
            this.previewPlayer.onloadeddata = () => {
                this.previewPopup.classList.remove('loading');
                this.previewPlayer.play().catch(err => {
                    console.warn('Autoplay prevented:', err);
                });
            };

            this.previewPlayer.onerror = () => {
                console.error('Failed to load video preview');
                this.hideVideoPreview();
            };
        }, 300); // 300ms delay
    }

    hideVideoPreview() {
        if (this.previewTimeout) {
            clearTimeout(this.previewTimeout);
            this.previewTimeout = null;
        }

        this.previewPopup.style.display = 'none';
        this.previewPlayer.pause();

        // Clear the video source to stop any loading/downloading
        this.previewSource.src = '';
        this.previewPlayer.load(); // Trigger load with empty source to stop network activity

        this.currentPreviewFilename = null;
        this.previewPopup.classList.remove('loading');
    }

    attachPreviewHandlers(element, filename) {
        element.addEventListener('mouseenter', (e) => {
            this.showVideoPreview(filename, element);
        });

        element.addEventListener('mouseleave', () => {
            this.hideVideoPreview();
        });
    }
}

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', () => {
    new ShotsDashboard();
});
