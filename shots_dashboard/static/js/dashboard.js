// Dashboard JavaScript

class ShotsDashboard {
    constructor() {
        this.socket = null;
        this.previewTimeout = null;
        this.currentPreviewFilename = null;
        this.autoplayEnabled = localStorage.getItem('audioAutoplayEnabled') === 'true';
        this.setupEventListeners();
        this.setupVideoPreview();
        this.setupAutoplayPermission();
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
                <div class="file-name" data-filename="${this.escapeHtml(file.name)}">${this.escapeHtml(file.name)}</div>
                <div class="file-path">${this.escapeHtml(file.path)}</div>
                <div class="file-time">${this.formatTime(file.last_updated)}</div>
            </div>
        `).join('');

        // Attach preview handlers to file names
        container.querySelectorAll('.file-name').forEach(el => {
            const filename = el.getAttribute('data-filename');
            if (filename) {
                this.attachPreviewHandlers(el, filename);
            }
        });
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

    updateTimelineHistory(history) {
        const currentInfo = document.getElementById('timeline-current-info');
        const currentClips = document.getElementById('timeline-current-clips');
        const historicalClips = document.getElementById('timeline-historical-clips');

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
                currentClips.innerHTML = history.current.clips.map(clip =>
                    `<span class="clip-badge" data-filename="${this.escapeHtml(clip)}">${this.escapeHtml(clip)}</span>`
                ).join('');

                // Attach preview handlers
                currentClips.querySelectorAll('.clip-badge').forEach(el => {
                    const filename = el.getAttribute('data-filename');
                    if (filename) {
                        this.attachPreviewHandlers(el, filename);
                    }
                });
            } else {
                currentClips.innerHTML = '<p class="empty-state">No clips in timeline</p>';
            }
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
        const currentSection = document.getElementById('timeline-current');
        const historicalSection = document.getElementById('timeline-historical');
        currentSection.style.display = show ? 'block' : 'none';
        historicalSection.style.display = show ? 'block' : 'none';
    }

    renderVisualTimeline(timelineData) {
        const container = document.getElementById('timeline-visual-canvas');

        if (!timelineData || !timelineData.tracks || timelineData.tracks.length === 0) {
            container.innerHTML = '<p class="empty-state">No timeline loaded yet</p>';
            return;
        }

        // Clear container
        container.innerHTML = '';

        // Create timeline visualization
        const duration = timelineData.duration;
        const trackHeight = 40;
        const headerWidth = 120;
        const timelineWidth = container.clientWidth - headerWidth - 40;
        const padding = 20;

        // Create wrapper
        const wrapper = document.createElement('div');
        wrapper.className = 'timeline-viz-wrapper';

        // Add timeline header with name and duration
        const header = document.createElement('div');
        header.className = 'timeline-viz-header';
        header.innerHTML = `
            <div class="timeline-viz-title">${this.escapeHtml(timelineData.name)}</div>
            <div class="timeline-viz-duration">Duration: ${this.formatDuration(duration)}</div>
        `;
        wrapper.appendChild(header);

        // Create time ruler
        const ruler = document.createElement('div');
        ruler.className = 'timeline-ruler';
        ruler.style.marginLeft = `${headerWidth}px`;

        // Add time markers
        const numMarkers = Math.min(10, Math.floor(duration / 5) + 1);
        for (let i = 0; i <= numMarkers; i++) {
            const time = (duration / numMarkers) * i;
            const marker = document.createElement('div');
            marker.className = 'time-marker';
            marker.style.left = `${(time / duration) * 100}%`;
            marker.innerHTML = `<span class="time-label">${this.formatDuration(time)}</span>`;
            ruler.appendChild(marker);
        }
        wrapper.appendChild(ruler);

        // Create tracks container
        const tracksContainer = document.createElement('div');
        tracksContainer.className = 'timeline-tracks-container';

        // Render each track
        timelineData.tracks.forEach((track, trackIdx) => {
            const trackRow = document.createElement('div');
            trackRow.className = `timeline-track ${track.kind.toLowerCase()}`;
            trackRow.style.height = `${trackHeight}px`;

            // Track header
            const trackHeader = document.createElement('div');
            trackHeader.className = 'track-header';
            trackHeader.style.width = `${headerWidth}px`;
            trackHeader.innerHTML = `
                <div class="track-name">${this.escapeHtml(track.name)}</div>
                <div class="track-kind">${track.kind}</div>
            `;
            trackRow.appendChild(trackHeader);

            // Track clips area
            const trackClips = document.createElement('div');
            trackClips.className = 'track-clips';
            trackClips.style.width = `${timelineWidth}px`;

            // Render clips
            track.clips.forEach(clip => {
                const clipEl = document.createElement('div');
                clipEl.className = 'timeline-clip';
                clipEl.setAttribute('data-filename', clip.name);

                const startPercent = (clip.start / duration) * 100;
                const widthPercent = (clip.duration / duration) * 100;

                clipEl.style.left = `${startPercent}%`;
                clipEl.style.width = `${widthPercent}%`;

                // Clip content
                const clipContent = document.createElement('div');
                clipContent.className = 'clip-content';
                clipContent.textContent = clip.name;
                clipContent.title = `${clip.name}\nStart: ${this.formatDuration(clip.start)}\nDuration: ${this.formatDuration(clip.duration)}`;

                clipEl.appendChild(clipContent);

                // Attach preview handlers
                this.attachPreviewHandlers(clipEl, clip.name);

                trackClips.appendChild(clipEl);
            });

            trackRow.appendChild(trackClips);
            tracksContainer.appendChild(trackRow);
        });

        wrapper.appendChild(tracksContainer);
        container.appendChild(wrapper);
    }

    formatDuration(seconds) {
        const totalSeconds = Math.floor(seconds);
        const frames = Math.round((seconds - totalSeconds) * 30); // Assume 30fps for display
        const mins = Math.floor(totalSeconds / 60);
        const secs = totalSeconds % 60;

        if (mins > 0) {
            return `${mins}:${secs.toString().padStart(2, '0')}:${frames.toString().padStart(2, '0')}`;
        } else {
            return `${secs}:${frames.toString().padStart(2, '0')}`;
        }
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

        if (data.timeline_visual) {
            this.renderVisualTimeline(data.timeline_visual);
        } else {
            // Clear timeline if none available
            this.renderVisualTimeline(null);
        }

        this.showStatus('Ready', 'success');
    }

    setupVideoPreview() {
        this.previewPopup = document.getElementById('video-preview-popup');
        this.videoPlayer = document.getElementById('video-preview-player');
        this.videoSource = document.getElementById('video-preview-source');
        this.audioPlayer = document.getElementById('audio-preview-player');
        this.audioSource = document.getElementById('audio-preview-source');
        this.imagePlayer = document.getElementById('image-preview-player');
        this.previewFilename = document.getElementById('video-preview-filename');

        // Log for debugging
        if (!this.previewPopup) console.error('Preview popup element not found');
        if (!this.imagePlayer) console.error('Image player element not found');
    }

    setupAutoplayPermission() {
        const overlay = document.getElementById('autoplay-overlay');
        const enableBtn = document.getElementById('enable-autoplay-btn');
        const skipBtn = document.getElementById('skip-autoplay-btn');

        // Show overlay if permission not granted yet
        if (!this.autoplayEnabled) {
            overlay.style.display = 'flex';
        }

        // Enable autoplay button
        enableBtn.addEventListener('click', async () => {
            try {
                // Create a silent audio context to get permission
                // This is the most reliable cross-browser method
                const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                const oscillator = audioContext.createOscillator();
                const gainNode = audioContext.createGain();

                // Connect and configure for silent playback
                oscillator.connect(gainNode);
                gainNode.connect(audioContext.destination);
                gainNode.gain.value = 0.001; // Nearly silent

                // Play briefly
                oscillator.start(0);
                oscillator.stop(audioContext.currentTime + 0.01);

                // Store permission
                this.autoplayEnabled = true;
                localStorage.setItem('audioAutoplayEnabled', 'true');

                // Hide overlay
                overlay.style.display = 'none';
                console.log('Audio autoplay enabled');
            } catch (error) {
                console.warn('Failed to enable autoplay:', error);
                // Even if it fails, grant permission since user clicked
                this.autoplayEnabled = true;
                localStorage.setItem('audioAutoplayEnabled', 'true');
                overlay.style.display = 'none';
            }
        });

        // Skip button
        skipBtn.addEventListener('click', () => {
            overlay.style.display = 'none';
        });
    }

    isAudioFile(filename) {
        const ext = filename.toLowerCase().split('.').pop();
        const audioExtensions = ['wav', 'mp3', 'ogg', 'oga', 'm4a', 'aiff', 'aif', 'flac', 'aac'];
        return audioExtensions.includes(ext);
    }

    isImageFile(filename) {
        const ext = filename.toLowerCase().split('.').pop();
        const imageExtensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'];
        return imageExtensions.includes(ext);
    }

    showVideoPreview(filename, element) {
        console.log('showVideoPreview called for:', filename);

        // Cancel any pending preview
        if (this.previewTimeout) {
            clearTimeout(this.previewTimeout);
        }

        // Delay showing preview to avoid flickering on quick mouse movements
        this.previewTimeout = setTimeout(() => {
            console.log('Showing preview for:', filename);
            this.currentPreviewFilename = filename;

            // Show loading state
            this.previewPopup.classList.add('loading');
            this.previewFilename.textContent = filename;

            // Determine media type
            const isAudio = this.isAudioFile(filename);
            const isImage = this.isImageFile(filename);

            // Position popup near the element
            const rect = element.getBoundingClientRect();
            const popupWidth = 400;
            const popupHeight = isAudio ? 100 : (isImage ? 350 : 300);  // Adjust for different types

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

            // Determine MIME type based on file extension
            const ext = filename.toLowerCase().split('.').pop();
            const mimeTypes = {
                'mp4': 'video/mp4',
                'webm': 'video/webm',
                'ogg': 'audio/ogg',
                'oga': 'audio/ogg',
                'wav': 'audio/wav',
                'mp3': 'audio/mpeg',
                'm4a': 'audio/mp4',
                'mov': 'video/webm',  // Transcoded
                'avi': 'video/webm',  // Transcoded
                'aiff': 'audio/ogg',  // Transcoded
                'aif': 'audio/ogg'    // Transcoded
            };
            const mimeType = mimeTypes[ext] || 'video/webm';

            // Show appropriate player and hide the others
            if (isImage) {
                this.imagePlayer.style.display = 'block';
                this.audioPlayer.style.display = 'none';
                this.videoPlayer.style.display = 'none';

                // Clear previous error handlers
                this.imagePlayer.onload = null;
                this.imagePlayer.onerror = null;

                // Load image
                this.imagePlayer.src = `/api/preview/${encodeURIComponent(filename)}`;

                this.imagePlayer.onload = () => {
                    this.previewPopup.classList.remove('loading');
                };

                this.imagePlayer.onerror = (e) => {
                    console.error('Failed to load image preview:', filename, e);
                    this.previewPopup.classList.remove('loading');
                    // Don't hide preview - just show error state
                };
            } else if (isAudio) {
                this.audioPlayer.style.display = 'block';
                this.videoPlayer.style.display = 'none';
                this.imagePlayer.style.display = 'none';

                // Clear previous error handlers
                this.audioPlayer.onloadeddata = null;
                this.audioPlayer.onerror = null;

                // Load audio
                this.audioSource.type = mimeType;
                this.audioSource.src = `/api/preview/${encodeURIComponent(filename)}`;
                this.audioPlayer.load();

                // Autoplay audio (unmuted if permission granted)
                this.audioPlayer.onloadeddata = () => {
                    this.previewPopup.classList.remove('loading');

                    // If autoplay is enabled, unmute before playing
                    if (this.autoplayEnabled) {
                        this.audioPlayer.muted = false;
                    }

                    // Start playback
                    this.audioPlayer.play().then(() => {
                        console.log('Audio preview playing, muted:', this.audioPlayer.muted);
                    }).catch(err => {
                        console.warn('Audio autoplay prevented:', err);
                        // Fall back to showing controls
                    });
                };

                this.audioPlayer.onerror = (e) => {
                    console.error('Failed to load audio preview:', filename, e);
                    this.previewPopup.classList.remove('loading');
                };
            } else {
                this.videoPlayer.style.display = 'block';
                this.audioPlayer.style.display = 'none';
                this.imagePlayer.style.display = 'none';

                // Clear previous error handlers
                this.videoPlayer.onloadeddata = null;
                this.videoPlayer.onerror = null;

                // Load video
                this.videoSource.type = mimeType;
                this.videoSource.src = `/api/preview/${encodeURIComponent(filename)}`;
                this.videoPlayer.load();

                // Start playing when loaded
                this.videoPlayer.onloadeddata = () => {
                    this.previewPopup.classList.remove('loading');
                    this.videoPlayer.play().catch(err => {
                        console.warn('Autoplay prevented:', err);
                    });
                };

                this.videoPlayer.onerror = (e) => {
                    console.error('Failed to load video preview:', filename, e);
                    this.previewPopup.classList.remove('loading');
                };
            }
        }, 300); // 300ms delay
    }

    hideVideoPreview() {
        if (this.previewTimeout) {
            clearTimeout(this.previewTimeout);
            this.previewTimeout = null;
        }

        this.previewPopup.style.display = 'none';

        // Pause and clear audio/video players
        this.videoPlayer.pause();
        this.audioPlayer.pause();

        // Reset muted state to default
        this.audioPlayer.muted = true;

        // Clear sources to stop any loading/downloading
        this.videoSource.src = '';
        this.audioSource.src = '';
        this.videoPlayer.load();
        this.audioPlayer.load();

        // Clear image using data URI to avoid "Invalid URI" error
        this.imagePlayer.src = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==';

        // Clear all event handlers to prevent interference
        this.videoPlayer.onloadeddata = null;
        this.videoPlayer.onerror = null;
        this.audioPlayer.onloadeddata = null;
        this.audioPlayer.onerror = null;
        this.imagePlayer.onload = null;
        this.imagePlayer.onerror = null;

        // Hide all players
        this.videoPlayer.style.display = 'none';
        this.audioPlayer.style.display = 'none';
        this.imagePlayer.style.display = 'none';

        this.currentPreviewFilename = null;
        this.previewPopup.classList.remove('loading');
    }

    attachPreviewHandlers(element, filename) {
        // Hover to show preview popup
        element.addEventListener('mouseenter', (e) => {
            this.showVideoPreview(filename, element);
        });

        element.addEventListener('mouseleave', () => {
            this.hideVideoPreview();
        });

        // Click to open preview in new tab
        element.addEventListener('click', (e) => {
            e.preventDefault();
            const previewUrl = `/api/preview/${encodeURIComponent(filename)}`;
            window.open(previewUrl, '_blank');
        });

        // Make it look clickable
        element.style.cursor = 'pointer';
    }
}

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', () => {
    new ShotsDashboard();
});
