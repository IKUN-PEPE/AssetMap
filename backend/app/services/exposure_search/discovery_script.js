(function() {
    if (window.__am_discovery_script_loaded) return;
    window.__am_discovery_script_loaded = true;

    // --- Configuration & State ---
    let captureModeActive = false;
    let capturedCount = 0;
    let lastHighlightedElement = null;

    // --- CSS Injection ---
    const style = document.createElement('style');
    style.innerHTML = `
        #am-discovery-toolbar {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 50px;
            background: #2c3e50;
            color: white;
            z-index: 2147483647;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            box-sizing: border-box;
            user-select: none;
        }
        #am-discovery-toolbar .logo {
            font-weight: bold;
            font-size: 18px;
            color: #409eff;
            margin-right: 20px;
        }
        #am-discovery-toolbar .controls {
            display: flex;
            align-items: center;
            gap: 20px;
        }
        #am-discovery-toolbar .status-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
        }
        #am-discovery-toolbar .toggle-btn {
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.3s;
            border: 1px solid transparent;
        }
        #am-discovery-toolbar .toggle-btn.off {
            background: #95a5a6;
            color: white;
        }
        #am-discovery-toolbar .toggle-btn.on {
            background: #67c23a;
            color: white;
            box-shadow: 0 0 8px rgba(103, 194, 58, 0.5);
        }
        #am-discovery-toolbar .count-badge {
            background: #e6a23c;
            color: white;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 12px;
            font-weight: bold;
        }

        /* Highlight classes */
        .am-highlight-target {
            outline: 2px dashed #409eff !important;
            outline-offset: 2px !important;
            cursor: pointer !important;
            transition: outline 0.1s !important;
        }

        /* Toast notifications */
        #am-toast-container {
            position: fixed;
            top: 60px;
            right: 20px;
            z-index: 2147483647;
            pointer-events: none;
        }
        .am-toast {
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 10px 20px;
            border-radius: 4px;
            margin-bottom: 10px;
            font-size: 14px;
            animation: am-fade-in-out 3s forwards;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            border-left: 4px solid #409eff;
        }
        @keyframes am-fade-in-out {
            0% { opacity: 0; transform: translateY(-20px); }
            10% { opacity: 1; transform: translateY(0); }
            90% { opacity: 1; transform: translateY(0); }
            100% { opacity: 0; transform: translateY(-20px); }
        }

        /* Prevent page content from being hidden */
        body {
            margin-top: 50px !important;
        }
    `;
    document.head.appendChild(style);

    // --- UI Construction ---
    const toolbar = document.createElement('div');
    toolbar.id = 'am-discovery-toolbar';
    toolbar.innerHTML = `
        <div class="controls">
            <span class="logo">AssetMap Discovery</span>
            <div id="am-capture-toggle" class="toggle-btn off">抓取模式: OFF</div>
        </div>
        <div class="status-item">
            已捕获线索: <span id="am-captured-count" class="count-badge">0</span>
        </div>
    `;
    document.body.appendChild(toolbar);

    const toastContainer = document.createElement('div');
    toastContainer.id = 'am-toast-container';
    document.body.appendChild(toastContainer);

    // --- Logic Functions ---
    function showToast(message) {
        const toast = document.createElement('div');
        toast.className = 'am-toast';
        toast.innerText = message;
        toastContainer.appendChild(toast);
        setTimeout(() => toast.remove(), 3500);
    }

    function updateUI() {
        const toggleBtn = document.getElementById('am-capture-toggle');
        const countBadge = document.getElementById('am-captured-count');
        
        if (captureModeActive) {
            toggleBtn.innerText = '抓取模式: ON';
            toggleBtn.className = 'toggle-btn on';
        } else {
            toggleBtn.innerText = '抓取模式: OFF';
            toggleBtn.className = 'toggle-btn off';
            if (lastHighlightedElement) {
                lastHighlightedElement.classList.remove('am-highlight-target');
                lastHighlightedElement = null;
            }
        }
        countBadge.innerText = capturedCount;
    }

    function extractMetadata(el) {
        // Find the most relevant anchor tag
        const anchor = el.tagName === 'A' ? el : el.querySelector('a');
        if (!anchor) return null;

        const url = anchor.href;
        const title = (anchor.innerText || anchor.textContent || '').trim();
        
        // Attempt to find snippet in search engine results
        // Google: .g, Bing: .b_algo
        let snippet = '';
        const container = el.closest('.g, .b_algo, .serp-item, div[data-hveid]');
        if (container) {
            // Get all text content and remove the title part to isolate snippet
            const fullText = container.innerText || container.textContent || '';
            snippet = fullText.replace(title, '').trim().substring(0, 300);
        } else {
            // Fallback: use parent text
            snippet = (el.parentElement.innerText || '').substring(0, 200);
        }

        return {
            title: title || '未知标题',
            url: url,
            snippet: snippet.replace(/\n/g, ' ').trim(),
            timestamp: new Date().toISOString(),
            source_page: window.location.href
        };
    }

    // --- Event Listeners ---
    document.getElementById('am-capture-toggle').addEventListener('click', (e) => {
        captureModeActive = !captureModeActive;
        updateUI();
        showToast(captureModeActive ? '抓取模式已开启，点击链接进行捕获' : '抓取模式已关闭');
        e.stopPropagation();
    });

    document.addEventListener('mouseover', (e) => {
        if (!captureModeActive) return;

        const target = e.target.closest('a, .g, .b_algo');
        if (target && target !== lastHighlightedElement) {
            if (lastHighlightedElement) {
                lastHighlightedElement.classList.remove('am-highlight-target');
            }
            target.classList.add('am-highlight-target');
            lastHighlightedElement = target;
        }
    }, true);

    document.addEventListener('mouseout', (e) => {
        if (!captureModeActive) return;
        if (lastHighlightedElement && !lastHighlightedElement.contains(e.relatedTarget)) {
            lastHighlightedElement.classList.remove('am-highlight-target');
            lastHighlightedElement = null;
        }
    }, true);

    document.addEventListener('click', (e) => {
        if (!captureModeActive) return;

        const target = e.target.closest('a, .g, .b_algo');
        if (target) {
            e.preventDefault();
            e.stopPropagation();

            const data = extractMetadata(target);
            if (data && data.url) {
                console.log('[AssetMap] Captured Clue:', data);
                
                if (typeof window.__am_record_clue === 'function') {
                    window.__am_record_clue(data);
                    capturedCount++;
                    updateUI();
                    showToast(`已捕获: ${data.title.substring(0, 20)}...`);
                } else {
                    console.warn('[AssetMap] window.__am_record_clue not found');
                    showToast('错误: 无法连接到后端');
                }
            }
        }
    }, true);

    console.log('[AssetMap] Discovery script injected and ready.');
})();
