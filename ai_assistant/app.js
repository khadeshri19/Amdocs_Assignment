// Global State
let queryChartInstance = null;

// DOM Elements
const connectionStatus = document.getElementById('connection-status');

// Settings Modal
const btnSettings = document.getElementById('btn-settings');
const settingsModal = document.getElementById('settings-modal');
const btnCloseModal = document.getElementById('btn-close-modal');
const btnSaveKey = document.getElementById('btn-save-key');
const btnClearKey = document.getElementById('btn-clear-key');
const geminiKeyInput = document.getElementById('gemini-key');

// AI Assistant Chat
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const chatMessages = document.getElementById('chat-messages');
const typingIndicator = document.getElementById('typing-indicator');
const suggestedQBtns = document.querySelectorAll('.suggested-q');

// AI Assistant Visual Workspaces
const queryChartCard = document.getElementById('query-chart-card');
const queryTableCard = document.getElementById('query-table-card');
const queryTableHeader = document.getElementById('query-table-header');
const queryTableBody = document.getElementById('query-table-body');
const pandasCodeContainer = document.getElementById('pandas-code-container');
const pandasCodeText = document.getElementById('pandas-code-text');
const btnCopyCode = document.getElementById('btn-copy-code');
const chartTypeBadge = document.getElementById('chart-type-badge');

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    loadApiKey();
    setupSettingsModal();
    setupChat();
});

// 1. API Key Handling
function loadApiKey() {
    const key = localStorage.getItem('gemini_api_key');
    if (key) {
        geminiKeyInput.value = key;
        connectionStatus.className = 'status-indicator gemini';
        connectionStatus.querySelector('.status-text').textContent = 'Gemini GenAI Engine';
    } else {
        connectionStatus.className = 'status-indicator local';
        connectionStatus.querySelector('.status-text').textContent = 'Local Rule-Based Engine';
    }
}

function getApiKey() {
    return localStorage.getItem('gemini_api_key') || null;
}

// 2. Settings Modal logic
function setupSettingsModal() {
    btnSettings.addEventListener('click', () => {
        settingsModal.style.display = 'flex';
    });
    
    btnCloseModal.addEventListener('click', () => {
        settingsModal.style.display = 'none';
    });
    
    settingsModal.addEventListener('click', (e) => {
        if (e.target === settingsModal) {
            settingsModal.style.display = 'none';
        }
    });

    btnSaveKey.addEventListener('click', () => {
        const key = geminiKeyInput.value.trim();
        if (key) {
            localStorage.setItem('gemini_api_key', key);
            addChatMessage('assistant', 'System Configuration: Gemini API Key successfully saved. The assistant will now use the official Gemini GenAI engine for processing queries!');
        } else {
            localStorage.removeItem('gemini_api_key');
        }
        loadApiKey();
        settingsModal.style.display = 'none';
    });
    
    btnClearKey.addEventListener('click', () => {
        localStorage.removeItem('gemini_api_key');
        geminiKeyInput.value = '';
        loadApiKey();
        settingsModal.style.display = 'none';
        addChatMessage('assistant', 'System Configuration: API Key cleared. Switched back to Local Rule-Based Engine.');
    });
}

// 3. Chat & Assistant Logic
function setupChat() {
    btnSend.addEventListener('click', handleChatSubmit);
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleChatSubmit();
    });

    // Suggested Questions
    suggestedQBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const queryText = btn.getAttribute('data-q');
            chatInput.value = queryText;
            handleChatSubmit();
        });
    });

    // Copy code button
    btnCopyCode.addEventListener('click', () => {
        navigator.clipboard.writeText(pandasCodeText.textContent)
            .then(() => {
                btnCopyCode.textContent = 'Copied!';
                setTimeout(() => btnCopyCode.textContent = 'Copy', 2000);
            });
    });
}

function handleChatSubmit() {
    const query = chatInput.value.trim();
    if (!query) return;

    // Add user bubble
    addChatMessage('user', query);
    chatInput.value = '';

    // Show typing indicator
    typingIndicator.style.display = 'flex';
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Call API
    const apiKey = getApiKey();
    fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query, api_key: apiKey })
    })
    .then(res => res.json())
    .then(data => {
        typingIndicator.style.display = 'none';
        
        if (data.success) {
            addChatMessage('assistant', data.answer);
            
            // Handle output visualizers
            updateQueryVisualizers(data);
        } else {
            addChatMessage('assistant', `Failed to execute: ${data.error || 'Unknown error'}`);
        }
    })
    .catch(err => {
        typingIndicator.style.display = 'none';
        addChatMessage('assistant', 'Error connecting to the backend server. Make sure the FastAPI application is running.');
        console.error(err);
    });
}

function addChatMessage(sender, text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender}`;
    
    // Convert markdown bold to HTML
    let formattedText = text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');

    msgDiv.innerHTML = `
        <div class="message-bubble">${formattedText}</div>
        <span class="message-meta">${sender === 'user' ? 'You' : 'Assistant'} • Just now</span>
    `;
    
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function updateQueryVisualizers(result) {
    // 1. Render Table if rows are present
    if (result.data && result.data.length > 0 && result.chart_type !== 'none') {
        queryTableCard.style.display = 'block';
        
        // Populate headers
        queryTableHeader.innerHTML = '';
        const columns = Object.keys(result.data[0]);
        columns.forEach(col => {
            const th = document.createElement('th');
            th.textContent = col;
            queryTableHeader.appendChild(th);
        });

        // Populate rows (max 10)
        queryTableBody.innerHTML = '';
        result.data.slice(0, 10).forEach(row => {
            const tr = document.createElement('tr');
            columns.forEach(col => {
                const td = document.createElement('td');
                const val = row[col];
                // Format numeric values
                if (typeof val === 'number' && !Number.isInteger(val)) {
                    td.textContent = val.toFixed(1);
                } else {
                    td.textContent = val;
                }
                tr.appendChild(td);
            });
            queryTableBody.appendChild(tr);
        });
        
        // Show syntax code container
        if (result.sql_or_pandas) {
            pandasCodeContainer.style.display = 'block';
            pandasCodeText.textContent = result.sql_or_pandas;
        } else {
            pandasCodeContainer.style.display = 'none';
        }
    } else {
        queryTableCard.style.display = 'none';
    }

    // 2. Render Chart
    if (result.chart_type && result.chart_type !== 'none' && result.data && result.data.length > 0) {
        queryChartCard.style.display = 'block';
        chartTypeBadge.textContent = result.chart_type + ' chart';
        renderQueryChart(result);
    } else {
        queryChartCard.style.display = 'none';
    }
}

function renderQueryChart(result) {
    const ctx = document.getElementById('query-chart').getContext('2d');
    
    // Destroy previous instance
    if (queryChartInstance) {
        queryChartInstance.destroy();
    }
    
    const chartType = result.chart_type;
    const xLabel = result.x_label;
    const yLabel = result.y_label;
    const data = result.data;
    
    // Extract labels & datasets
    let labels = [];
    let chartValues = [];
    
    if (chartType === 'scatter') {
        // Scatter needs x, y coordinates
        const scatterData = data.map(item => ({
            x: item[xLabel] || item['Credit amount'],
            y: item[yLabel] || item['Duration'],
            label: item['Housing'] || ''
        }));
        
        queryChartInstance = new Chart(ctx, {
            type: 'scatter',
            data: {
                datasets: [{
                    label: 'Borrowers',
                    data: scatterData,
                    backgroundColor: 'rgba(99, 102, 241, 0.6)',
                    borderColor: '#6366f1',
                    borderWidth: 1,
                    pointRadius: 5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { title: { display: true, text: xLabel, color: '#9ca3af' }, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af' } },
                    y: { title: { display: true, text: yLabel, color: '#9ca3af' }, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af' } }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
        return;
    }
    
    // Bar & Pie handling
    const dataKeys = Object.keys(data[0]);
    const labelKey = xLabel || dataKeys[0];
    const valKey = yLabel || dataKeys[1];
    
    labels = data.map(row => row[labelKey]);
    chartValues = data.map(row => row[valKey]);

    const themeColors = [
        '#6366f1', '#3b82f6', '#10b981', '#f59e0b', '#ef4444', 
        '#8b5cf6', '#ec4899', '#14b8a6', '#06b6d4', '#f43f5e'
    ];

    queryChartInstance = new Chart(ctx, {
        type: chartType === 'pie' ? 'pie' : 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: valKey,
                data: chartValues,
                backgroundColor: chartType === 'pie' ? themeColors.slice(0, labels.length) : 'rgba(99, 102, 241, 0.85)',
                borderColor: chartType === 'pie' ? '#111827' : '#6366f1',
                borderWidth: 1,
                borderRadius: chartType === 'pie' ? 0 : 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: chartType === 'pie',
                    position: 'right',
                    labels: { color: '#9ca3af', font: { family: 'Inter' } }
                }
            },
            scales: chartType === 'pie' ? {} : {
                x: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#9ca3af' } },
                y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#9ca3af' } }
            }
        }
    });
}
