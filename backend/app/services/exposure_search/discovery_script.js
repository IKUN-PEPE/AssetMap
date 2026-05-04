(function() {
    if (window.__am_discovery_script_loaded) return;
    window.__am_discovery_script_loaded = true;

    let capturedCount = 0;
    let isRiskControlled = false;
    let captureModeActive = true;
    let panelVisible = true;
    let finishPending = false;
    let isDragging = false;
    let startX;
    let startY;
    let initialX;
    let initialY;
    let taskProgress = {
        progressPercent: 0,
        completedQueries: 0,
        totalQueries: 0,
        currentQuery: '',
        nextQuery: '',
        visible: false,
    };

    const container = document.createElement('div');
    container.id = 'am-discovery-root';
    container.style.cssText = [
        'position:fixed',
        'top:50%',
        'right:20px',
        'width:auto',
        'height:auto',
        'z-index:2147483647',
        'pointer-events:none',
        'display:block !important',
        'visibility:visible !important',
        'isolation:isolate',
        'transform:translateY(-50%)',
    ].join(';') + ';';

    const lockMethod = () => { console.warn('[AssetMap] Persistence Lock Active.'); };
    Object.defineProperty(container, 'remove', { value: lockMethod, writable: false, configurable: false });

    const shadow = container.attachShadow({ mode: 'closed' });

    const style = document.createElement('style');
    style.textContent = `
        :host { all: initial; }
        #am-shell {
            position: relative;
            z-index: 2147483647;
            isolation: isolate;
            pointer-events: none;
            font-family: Arial, sans-serif;
        }
        .ball {
            pointer-events: auto;
            width: 60px;
            height: 60px;
            background: #409eff;
            border-radius: 50%;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: move;
            user-select: none;
            color: white;
            position: relative;
            z-index: 2147483647;
            transition: transform 0.2s;
        }
        .ball:hover { transform: scale(1.05); }
        .ball.active { background: #67c23a; }
        .ball.risk { background: #e6a23c; animation: pulse-red 2s infinite; }
        .panel {
            pointer-events: auto;
            position: absolute;
            top: 50%;
            right: 72px;
            transform: translateY(-50%);
            width: 260px;
            background: #2c3e50;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.4);
            display: none;
            flex-direction: column;
            gap: 10px;
            color: white;
            z-index: 2147483647;
        }
        .panel.visible { display: flex; }
        .title {
            font-size: 14px;
            font-weight: bold;
            border-bottom: 1px solid #555;
            padding-bottom: 5px;
            margin-bottom: 5px;
        }
        .btn {
            padding: 8px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            font-weight: bold;
            border: none;
            transition: 0.2s;
            text-align: center;
        }
        .btn-capture { background: #409eff; color: white; }
        .btn-toggle { background: #67c23a; color: white; }
        .btn-toggle.off { background: #95a5a6; }
        .btn-resume { background: #f39c12; color: white; display: none; }
        .btn-finish { background: #e74c3c; color: white; }
        .btn-nav { background: #34495e; color: white; }
        .btn[disabled] { opacity: 0.6; cursor: not-allowed; }
        .nav-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }
        .stats { font-size: 12px; opacity: 0.85; margin-top: 5px; }
        .badge { color: #f1c40f; font-weight: bold; }
        .progress-box {
            display: none;
            gap: 6px;
            flex-direction: column;
            margin-bottom: 6px;
        }
        .progress-box.visible { display: flex; }
        .progress-label {
            font-size: 12px;
            opacity: 0.85;
            line-height: 1.4;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .progress-track {
            width: 100%;
            height: 8px;
            border-radius: 999px;
            background: rgba(255,255,255,0.14);
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, #67c23a, #409eff);
            transition: width 0.2s ease;
        }
        #toast-container {
            position: fixed;
            top: 50%;
            right: 92px;
            transform: translateY(-220px);
            display: flex;
            flex-direction: column;
            gap: 10px;
            pointer-events: none;
            z-index: 2147483647;
        }
        .toast {
            background: rgba(46, 204, 113, 0.92);
            color: white;
            padding: 8px 16px;
            border-radius: 4px;
            font-size: 13px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            animation: fadeIn 0.3s forwards;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulse-red {
            0% { box-shadow: 0 0 0 0 rgba(230, 162, 60, 0.7); }
            70% { box-shadow: 0 0 0 15px rgba(230, 162, 60, 0); }
            100% { box-shadow: 0 0 0 0 rgba(230, 162, 60, 0); }
        }
        :host-context(html[am-mode="on"]) a:hover {
            outline: 2px dashed #409eff !important;
            background: rgba(64, 158, 255, 0.1) !important;
        }
    `;
    shadow.appendChild(style);

    function syncModeToAttr() {
        document.documentElement.setAttribute('am-mode', captureModeActive ? 'on' : 'off');
    }

    function getExtensionFromUrl(url) {
        try {
            const parsed = new URL(url, window.location.href);
            const pathname = parsed.pathname || '';
            const lastSegment = pathname.split('/').pop() || '';
            const parts = lastSegment.split('.');
            if (parts.length < 2) return '';
            return (parts.pop() || '').toLowerCase();
        } catch (_error) {
            return '';
        }
    }

    function buildPreviewUrl(url) {
        const extension = getExtensionFromUrl(url);
        if (!extension) return null;
        if (extension === 'pdf') return url;
        if (['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].includes(extension)) {
            return `https://view.officeapps.live.com/op/view.aspx?src=${encodeURIComponent(url)}`;
        }
        if (['csv', 'sql', 'json'].includes(extension)) {
            return `/api/v1/exposure-search/preview-text?url=${encodeURIComponent(url)}&file_type=${encodeURIComponent(extension)}`;
        }
        return null;
    }

    function clickNextPageButton() {
        const selectors = [
            'a[rel="next"]',
            'button[rel="next"]',
            'a[aria-label*="Next"]',
            'button[aria-label*="Next"]',
            'a[aria-label*="下一页"]',
            'button[aria-label*="下一页"]',
            '.nicon[title*="下一页"]',
            '.sb_pagN',
            'a#pnnext',
            'a.next',
            '.next > a',
            '.pagination-next a',
            '.pager-next a',
            '.pager .next',
        ];
        for (const selector of selectors) {
            const element = document.querySelector(selector);
            if (element instanceof HTMLElement && !element.hasAttribute('disabled')) {
                element.click();
                return true;
            }
        }

        const textCandidates = Array.from(document.querySelectorAll('a, button')).find((node) => {
            const text = (node.textContent || '').trim();
            return ['下一页', '下页', 'Next', '>', '›'].includes(text);
        });
        if (textCandidates instanceof HTMLElement && !textCandidates.hasAttribute('disabled')) {
            textCandidates.click();
            return true;
        }
        return false;
    }

    function fallbackNextPageNavigation() {
        try {
            const url = new URL(window.location.href);
            if (url.hostname.includes('baidu.com')) {
                const current = Number(url.searchParams.get('pn') || '0');
                url.searchParams.set('pn', String(current + 10));
                window.location.href = url.toString();
                return true;
            }
            if (url.hostname.includes('google.com')) {
                const current = Number(url.searchParams.get('start') || '0');
                url.searchParams.set('start', String(current + 10));
                window.location.href = url.toString();
                return true;
            }
            if (url.hostname.includes('bing.com')) {
                const current = Number(url.searchParams.get('first') || '1');
                url.searchParams.set('first', String(current + 10));
                window.location.href = url.toString();
                return true;
            }
            if (url.hostname.includes('github.com')) {
                const current = Number(url.searchParams.get('p') || '1');
                url.searchParams.set('p', String(current + 1));
                window.location.href = url.toString();
                return true;
            }
        } catch (_error) {
            return false;
        }
        return false;
    }

    function detectTaskId() {
        try {
            const href = String(window.location.href || '');
            const queryMatch = href.match(/[?&]task_id=([a-zA-Z0-9-]+)/);
            if (queryMatch) return queryMatch[1];
            const hashMatch = href.match(/[?#/](?:task|task_id)\/([a-zA-Z0-9-]+)/);
            return hashMatch ? hashMatch[1] : '';
        } catch (_error) {
            return '';
        }
    }

    function detectActiveSearchQuery() {
        try {
            const currentUrl = new URL(window.location.href);
            const host = currentUrl.hostname.toLowerCase();
            if (host.includes('bing.com')) return currentUrl.searchParams.get('q') || '';
            if (host.includes('baidu.com')) return currentUrl.searchParams.get('wd') || '';
            if (host.includes('google.com')) return currentUrl.searchParams.get('q') || '';
            if (host.includes('github.com')) return currentUrl.searchParams.get('q') || '';
            return currentUrl.searchParams.get('q') || currentUrl.searchParams.get('wd') || '';
        } catch (_error) {
            return '';
        }
    }

    const shell = document.createElement('div');
    shell.id = 'am-shell';
    shadow.appendChild(shell);

    const ball = document.createElement('div');
    ball.className = 'ball active';
    ball.innerHTML = `
        <svg viewBox="0 0 1024 1024" width="32" height="32" aria-hidden="true">
            <path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64z m0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z" fill="currentColor"></path>
            <path d="M512 192c-176.7 0-320 143.3-320 320s143.3 320 320 320 320-143.3 320-320-143.3-320-320-320z m0 576c-141.4 0-256-114.6-256-256s114.6-256 256-256 256 114.6 256 256-114.6 256-256 256z" fill="currentColor"></path>
        </svg>
    `;
    shell.appendChild(ball);

    const panel = document.createElement('div');
    panel.className = 'panel visible';
    panel.innerHTML = `
        <div class="title">AssetMap Discovery</div>
        <div id="progress-box" class="progress-box">
            <div class="progress-track"><div id="progress-fill" class="progress-fill"></div></div>
            <div id="progress-summary" class="progress-label">搜索进度: 0/0 (0%)</div>
            <div id="current-query" class="progress-label">当前语法: -</div>
            <div id="next-query" class="progress-label">下一条语法: -</div>
        </div>
        <div class="nav-row">
            <button id="nav-back" class="btn btn-nav">上一页</button>
            <button id="nav-forward" class="btn btn-nav">下一页</button>
        </div>
        <button id="cap-page" class="btn btn-capture">捕获当前页</button>
        <button id="toggle" class="btn btn-toggle">抓取模式: ON</button>
        <button id="resume" class="btn btn-resume">风控恢复</button>
        <button id="finish" class="btn btn-finish">完成并继续</button>
        <div class="stats">已捕获线索: <span id="count" class="badge">0</span></div>
    `;
    shell.appendChild(panel);

    const toastContainer = document.createElement('div');
    toastContainer.id = 'toast-container';
    shell.appendChild(toastContainer);

    const btnNavBack = panel.querySelector('#nav-back');
    const btnNavForward = panel.querySelector('#nav-forward');
    const btnCapPage = panel.querySelector('#cap-page');
    const btnToggle = panel.querySelector('#toggle');
    const btnResume = panel.querySelector('#resume');
    const btnFinish = panel.querySelector('#finish');
    const countEl = panel.querySelector('#count');
    const progressBox = panel.querySelector('#progress-box');
    const progressFill = panel.querySelector('#progress-fill');
    const progressSummary = panel.querySelector('#progress-summary');
    const currentQueryEl = panel.querySelector('#current-query');
    const nextQueryEl = panel.querySelector('#next-query');

    function showToast(message) {
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.innerText = message;
        toastContainer.appendChild(toast);
        setTimeout(() => toast.remove(), 2500);
    }

    function updateUI() {
        btnToggle.innerText = captureModeActive ? '抓取模式: ON' : '抓取模式: OFF';
        btnToggle.className = 'btn btn-toggle' + (captureModeActive ? '' : ' off');
        btnFinish.innerText = finishPending ? '处理中...' : '完成并继续';
        btnFinish.disabled = finishPending;
        countEl.innerText = String(capturedCount);
        progressBox.classList.toggle('visible', taskProgress.visible);
        progressFill.style.width = `${taskProgress.progressPercent}%`;
        progressSummary.innerText = `搜索进度: ${taskProgress.completedQueries}/${taskProgress.totalQueries} (${taskProgress.progressPercent}%)`;
        currentQueryEl.innerText = `当前语法: ${taskProgress.currentQuery || '-'}`;
        nextQueryEl.innerText = `下一条语法: ${taskProgress.nextQuery || '-'}`;
        currentQueryEl.title = taskProgress.currentQuery || '';
        nextQueryEl.title = taskProgress.nextQuery || '';
        ball.className = 'ball' + (captureModeActive ? ' active' : '') + (isRiskControlled ? ' risk' : '');
        btnResume.style.display = isRiskControlled ? 'block' : 'none';
        panel.classList.toggle('visible', panelVisible);
        syncModeToAttr();
    }

    async function pollTaskProgress() {
        const taskId = detectTaskId();
        if (!taskId) return;
        try {
            const response = await fetch(`/api/v1/exposure-search/tasks/${encodeURIComponent(taskId)}`, {
                credentials: 'include',
            });
            if (!response.ok) return;
            const task = await response.json();
            taskProgress = {
                progressPercent: Number(task.progress_percent || 0),
                completedQueries: Number(task.completed_queries || 0),
                totalQueries: Number(task.total_queries || 0),
                currentQuery: String(task.current_query || ''),
                nextQuery: String(task.next_query || ''),
                visible: Number(task.total_queries || 0) > 0,
            };
            updateUI();
        } catch (_error) {
            // Keep overlay usable if polling fails.
        }
    }

    ball.onmousedown = (event) => {
        isDragging = false;
        startX = event.clientX;
        startY = event.clientY;
        const rect = container.getBoundingClientRect();
        initialX = rect.left;
        initialY = rect.top;

        document.onmousemove = (moveEvent) => {
            isDragging = true;
            const dx = moveEvent.clientX - startX;
            const dy = moveEvent.clientY - startY;
            container.style.left = (initialX + dx) + 'px';
            container.style.top = (initialY + dy) + 'px';
            container.style.transform = 'none';
            container.style.bottom = 'auto';
            container.style.right = 'auto';
        };

        document.onmouseup = () => {
            document.onmousemove = null;
            document.onmouseup = null;
        };
    };

    ball.onclick = () => {
        if (!isDragging) {
            panelVisible = !panelVisible;
            updateUI();
        }
    };

    btnNavBack.onclick = () => {
        window.history.back();
    };

    btnNavForward.onclick = () => {
        if (clickNextPageButton()) return;
        if (fallbackNextPageNavigation()) return;
        window.history.forward();
    };

    btnCapPage.onclick = async () => {
        await window.__am_record_clue?.({
            title: document.title || '当前页面',
            url: window.location.href,
            source_page: window.location.href,
            query: detectActiveSearchQuery(),
            snippet: document.body ? document.body.innerText.substring(0, 500) : ''
        });
        capturedCount++;
        updateUI();
        showToast('已捕获当前页面');
    };

    btnToggle.onclick = () => {
        captureModeActive = !captureModeActive;
        updateUI();
    };

    btnFinish.onclick = async () => {
        if (finishPending) return;
        finishPending = true;
        updateUI();
        try {
            await window.__am_finish_and_continue?.();
            panelVisible = false;
            showToast('已跳过当前页，进入下一搜索语法');
        } catch (_error) {
            showToast('结束当前页失败');
        } finally {
            finishPending = false;
            updateUI();
        }
    };

    btnResume.onclick = () => {
        window.__am_resume_auto?.();
        isRiskControlled = false;
        updateUI();
    };

    document.addEventListener('click', async (event) => {
        if (!captureModeActive) return;

        const anchor = event.target && event.target.closest ? event.target.closest('a') : null;
        if (anchor && anchor.href && !anchor.href.startsWith('javascript:')) {
            if (event.composedPath().includes(container)) return;

            const data = {
                title: anchor.innerText.trim() || anchor.title || '链接线索',
                url: anchor.href,
                source_page: window.location.href,
                query: detectActiveSearchQuery()
            };
            const previewUrl = buildPreviewUrl(anchor.href);

            if ((!event.ctrlKey && !event.metaKey && !anchor.target) || anchor.target === '_self') {
                event.preventDefault();
                event.stopPropagation();

                try {
                    await window.__am_record_clue?.(data);
                    capturedCount++;
                    updateUI();
                    showToast('已记录线索');
                    setTimeout(() => {
                        if (previewUrl) {
                            window.open(previewUrl, '_blank', 'noopener');
                        } else {
                            window.location.href = anchor.href;
                        }
                    }, 100);
                } catch (_error) {
                    if (previewUrl) {
                        window.open(previewUrl, '_blank', 'noopener');
                    } else {
                        window.location.href = anchor.href;
                    }
                }
            } else {
                if (previewUrl) {
                    event.preventDefault();
                    event.stopPropagation();
                }
                window.__am_record_clue?.(data);
                capturedCount++;
                updateUI();
                showToast('已记录线索');
                if (previewUrl) {
                    window.open(previewUrl, '_blank', 'noopener');
                }
            }
        }
    }, true);

    function mount() {
        if (!document.documentElement) {
            setTimeout(mount, 50);
            return;
        }

        document.documentElement.appendChild(container);
        updateUI();
        pollTaskProgress();

        setInterval(() => {
            if (container.parentNode !== document.documentElement) {
                document.documentElement.appendChild(container);
            }

            const text = (document.body && document.body.innerText ? document.body.innerText : '').toLowerCase();
            const hasRisk = ['captcha', 'verify', '人机验证', '安全验证', '登录', 'sign in'].some((keyword) => text.includes(keyword));
            if (hasRisk !== isRiskControlled) {
                isRiskControlled = hasRisk;
                updateUI();
            }
        }, 500);

        setInterval(pollTaskProgress, 1500);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mount);
    } else {
        mount();
    }
})();
