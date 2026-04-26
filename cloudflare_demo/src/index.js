const htmlContent = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Triple A Chatbot MVP</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.min.js"></script>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; margin: 0; padding: 20px; display: flex; height: 100vh; box-sizing: border-box; gap: 20px; justify-content: center; }
        
        /* Auth Overlay */
        #auth-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; display: flex; justify-content: center; align-items: center; }
        .auth-box { background: white; padding: 30px; border-radius: 10px; width: 350px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
        .auth-box h2 { margin-top: 0; color: #333; }
        .auth-box select, .auth-box input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; }
        .auth-box button { width: 100%; padding: 10px; background: #0056b3; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; transition: 0.3s; }
        .auth-box button:hover { background: #004494; }
        
        .chat-container { width: 100%; max-width: 600px; background: white; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); display: flex; flex-direction: column; height: 100%; transition: width 0.3s, max-width 0.3s; }
        .chat-container.split { width: 40%; max-width: none; }
        .pdf-container { width: 60%; background: white; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); display: none; flex-direction: column; height: 100%; position: relative; overflow: auto; align-items: center; padding: 20px; }
        
        .header { background: #0056b3; color: white; padding: 15px; border-radius: 10px 10px 0 0; text-align: center; position: relative; }
        .header h2 { margin: 0; font-size: 1.2rem; }
        .header-sub { font-size: 0.8rem; opacity: 0.8; margin-top: 5px; }
        
        /* Admin controls */
        #admin-controls { display: none; background: #f0f0f0; padding: 10px 15px; border-bottom: 1px solid #ddd; font-size: 0.9em; }
        #admin-controls input[type="file"] { margin-right: 10px; }
        #admin-controls input[type="text"] { padding: 5px; width: 120px; border: 1px solid #ccc; outline: none; margin-right: 10px; }
        #admin-controls button { padding: 5px 10px; font-size: 0.9em; background: #28a745; border:none; color:#fff; border-radius:3px; cursor:pointer;}
        #ingest-status { margin-left: 10px; font-style: italic; color: #555; }
        
        .chat-box { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 15px; }
        .message { max-width: 80%; padding: 12px; border-radius: 8px; line-height: 1.4; word-wrap:break-word;}
        .user-msg { background: #e1f5fe; align-self: flex-end; border: 1px solid #b3e5fc; }
        .bot-msg { background: #f5f5f5; align-self: flex-start; border: 1px solid #e0e0e0; }
        .citations { font-size: 0.8em; color: #555; margin-top: 8px; padding-top: 8px; border-top: 1px solid #ddd; }
        .citations a { color: #0056b3; text-decoration: underline; cursor: pointer; display: inline-block; margin-top: 5px; }
        .input-area { display: flex; padding: 15px; border-top: 1px solid #ddd; background: #fff; border-radius: 0 0 10px 10px; flex-shrink: 0; }
        input[type="text"]#query-input { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 5px; margin-right: 10px; outline: none; }
        .input-area button { padding: 10px 20px; background: #0056b3; color: white; border: none; border-radius: 5px; cursor: pointer; transition: 0.3s; }
        .input-area button:hover { background: #004494; }
        .loading { align-self: flex-start; color: #888; font-style: italic; display: none; }
        
        #pdfCanvas { border: 1px solid #ddd; }
        .pdf-wrapper { position: relative; display: inline-block; }
        .highlight-box { position: absolute; background-color: rgba(255, 255, 0, 0.4); border: 2px solid #ffcc00; pointer-events: none; }
        
        /* Directory Table Styles */
        #directory-table { font-size: 0.85em; border: 1px solid #ddd; border-radius: 5px; overflow: hidden; }
        #directory-table th { background: #eee; padding: 8px; font-weight: bold; }
        #directory-table td { background: #fafafa; }
        #directory-table tr:hover td { background: #f0f0f0; }
        .delete-btn { background: #dc3545 !important; margin: 0; padding: 2px 8px !important; }
        .delete-btn:hover { background: #c82333 !important; }
        .badge { padding: 2px 6px; border-radius: 4px; font-size: 0.8em; color: white; display: inline-block; }
        .badge-green { background: #28a745; }
        .badge-yellow { background: #ffc107; color: #333; }
        .sync-btn { background: #007bff !important; margin-right: 5px; padding: 2px 8px !important; }
    </style>
</head>
<body>

<div id="auth-overlay">
    <div class="auth-box">
        <h2>Welcome to Triple A</h2>
        <select id="role-select" onchange="toggleAuthFields()">
            <option value="Client">Client Mode</option>
            <option value="Admin">Admin Mode</option>
        </select>
        
        <div id="client-fields">
            <input type="text" id="client-name" placeholder="Enter your Name (e.g. John Doe)">
        </div>
        
        <div id="admin-fields" style="display: none;">
            <input type="password" id="admin-pin" placeholder="Enter Admin PIN">
        </div>
        
        <button onclick="login()">Enter Chat</button>
    </div>
</div>

<div class="chat-container">
    <div class="header">
        <h2>Triple A Chatbot</h2>
        <div class="header-sub" id="header-identity">Not logged in</div>
    </div>
    
    <div id="admin-controls" style="display:none;">
        <strong>Admin Tools:</strong>
        <div style="margin-top: 5px;">
            Target Client Context: <input type="text" id="admin-target-client" placeholder="Global Context...">
        </div>
        <div style="margin-top: 5px; display:flex; align-items:center;">
            <input type="file" id="pdf-upload" accept="application/pdf">
            <button onclick="ingestPdf()">Ingest PDF</button>
        </div>
        <div id="ingest-status" style="margin-top: 5px; font-size: 0.85em;"></div>
        <button onclick="refreshDirectory()" style="margin-top:10px;">Refresh Directory</button>
        <table id="directory-table" style="margin-top:10px; width:100%; border-collapse:collapse; display:none;">
            <thead><tr><th style="border-bottom:1px solid #ccc; text-align:left;">Document</th><th style="border-bottom:1px solid #ccc; text-align:left;">Status</th><th style="border-bottom:1px solid #ccc;">Actions</th></tr></thead>
            <tbody></tbody>
        </table>
    </div>
    
    <div class="chat-box" id="chat-box">
        <div class="message bot-msg">Hello! Please wait while you log in to view related documents.</div>
        <div class="loading" id="loading">Searching knowledge base...</div>
    </div>
    <div class="input-area">
        <input type="text" id="query-input" placeholder="e.g., What forms do I need to submit?" onkeypress="handleKeyPress(event)">
        <button onclick="sendQuery()">Ask</button>
    </div>
</div>

<div class="pdf-container">
    <h3 style="color: #666; margin-top: 0; margin-bottom: 20px;">Document Viewer</h3>
    <div id="pdf-placeholder" style="color: #999; margin-top: auto; margin-bottom: auto;">Click a citation link to view the document and highlighted text.</div>
    <div class="pdf-wrapper" id="pdf-wrapper" style="display: none;">
        <canvas id="pdfCanvas"></canvas>
        <div id="highlight" class="highlight-box" style="display: none;"></div>
    </div>
</div>

<script>
    const API_URL = '/api/chat'; 
    const INGEST_URL = '/api/ingest';

    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.worker.min.js';
    let currentPdfDoc = null;
    
    let userRole = null;
    let userClientName = null;
    
    function toggleAuthFields() {
        const role = document.getElementById('role-select').value;
        if(role === 'Admin') {
            document.getElementById('client-fields').style.display = 'none';
            document.getElementById('admin-fields').style.display = 'block';
        } else {
            document.getElementById('client-fields').style.display = 'block';
            document.getElementById('admin-fields').style.display = 'none';
        }
    }
    
    function login() {
        const role = document.getElementById('role-select').value;
        const chatBox = document.getElementById('chat-box');
        
        if(role === 'Admin') {
            const pin = document.getElementById('admin-pin').value;
            if(pin !== 'admin123') {
                alert('Invalid Admin PIN');
                return;
            }
            userRole = 'Admin';
            userClientName = 'Admin';
            document.getElementById('admin-controls').style.display = 'block';
            document.getElementById('header-identity').textContent = 'Role: Administrator';
            
            chatBox.innerHTML = '<div class="message bot-msg">Welcome Admin. You may query documents or upload new ones.</div><div class="loading" id="loading">Searching...</div>';
            refreshDirectory();
        } else {
            const cName = document.getElementById('client-name').value.trim();
            if(!cName) {
                alert('Please enter your Client Name');
                return;
            }
            userRole = 'Client';
            userClientName = cName;
            document.getElementById('header-identity').textContent = 'Role: Client | Name: ' + cName;
            
            chatBox.innerHTML = \`<div class="message bot-msg">Welcome, \${cName}. I am your automated assistant. Ask me anything regarding your documents.</div><div class="loading" id="loading">Searching...</div>\`;
        }
        document.getElementById('auth-overlay').style.display = 'none';
    }

    async function ingestPdf() {
        const fileInput = document.getElementById('pdf-upload');
        const targetClient = document.getElementById('admin-target-client').value.trim();
        const statusEl = document.getElementById('ingest-status');
        
        if (!fileInput.files.length) {
            statusEl.style.color = 'red';
            statusEl.textContent = 'Please select a file first.';
            return;
        }
        const file = fileInput.files[0];
        statusEl.style.color = 'blue';
        statusEl.textContent = 'Parsing PDF in browser...';
        
        try {
            const arrayBuffer = await file.arrayBuffer();
            const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
            let blocks = [];
            
            for (let i = 1; i <= pdf.numPages; i++) {
                statusEl.textContent = \`Parsing page \${i}/\${pdf.numPages}...\`;
                const page = await pdf.getPage(i);
                const textContent = await page.getTextContent();
                
                textContent.items.forEach(item => {
                    const str = item.str.trim();
                    if (str.length > 5) {
                        const tx = item.transform[4];
                        const ty = item.transform[5];
                        const h = item.transform[3] || 10;
                        const x0 = tx;
                        const y0 = ty;
                        const x1 = tx + item.width;
                        const y1 = ty + Math.abs(h);
                        blocks.push({ text: str, page: i, bbox: [x0, y0, x1, y1] });
                    }
                });
            }
            
            statusEl.textContent = 'Sending to Cloudflare processing pipeline (~1 min)...';
            
            const formData = new FormData();
            formData.append('pdfFile', file);
            formData.append('fileName', file.name);
            formData.append('clientName', targetClient || "public");
            formData.append('blocks', JSON.stringify(blocks));

            const response = await fetch(INGEST_URL, {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            if (data.error) {
                statusEl.style.color = 'red';
                statusEl.textContent = 'Ingest Error: ' + data.error;
            } else {
                statusEl.style.color = 'green';
                statusEl.textContent = 'Success! ' + data.nodesInserted + ' chunks ingested uniquely for ' + (targetClient || "public") + '.';
            }
        } catch (e) {
            console.error(e);
            statusEl.style.color = 'red';
            statusEl.textContent = 'Failed to parse PDF.';
        }
    }

    async function loadAndHighlightPdf(url, pageNum, bboxJson) {
        document.querySelector('.chat-container').classList.add('split');
        document.querySelector('.pdf-container').style.display = 'flex';
        document.getElementById('pdf-placeholder').style.display = 'none';
        document.getElementById('pdf-wrapper').style.display = 'inline-block';
        document.getElementById('highlight').style.display = 'none';
        
        const loadingTask = pdfjsLib.getDocument(url);
        try {
            currentPdfDoc = await loadingTask.promise;
            const page = await currentPdfDoc.getPage(parseInt(pageNum) || 1);
            
            const scale = 1.3;
            const viewport = page.getViewport({ scale: scale });
            
            const canvas = document.getElementById('pdfCanvas');
            const context = canvas.getContext('2d');
            canvas.height = viewport.height;
            canvas.width = viewport.width;
            
            await page.render({ canvasContext: context, viewport: viewport }).promise;
            
            if(bboxJson) {
                const bbox = JSON.parse(bboxJson);
                const [x0, y0, x1, y1] = bbox;
                
                const p1 = viewport.convertToViewportPoint(x0, y0);
                const p2 = viewport.convertToViewportPoint(x1, y1);
                
                const hl = document.getElementById('highlight');
                hl.style.left = Math.min(p1[0], p2[0]) + 'px';
                hl.style.top = Math.min(p1[1], p2[1]) + 'px';
                hl.style.width = Math.abs(p2[0] - p1[0]) + 'px';
                hl.style.height = Math.abs(p2[1] - p1[1]) + 'px';
                hl.style.display = 'block';
                
                document.querySelector('.pdf-container').scrollTop = Math.max(0, Math.min(p1[1], p2[1]) - 40);
            }
        } catch(e) {
            console.error("Error rendering PDF:", e);
        }
    }

    function handleKeyPress(e) { if(e.key === 'Enter') sendQuery(); }

    async function sendQuery() {
        const inputField = document.getElementById('query-input');
        const query = inputField.value.trim();
        if(!query) return;

        addMessage(query, 'user-msg');
        inputField.value = '';
        const loading = document.getElementById('loading');
        loading.style.display = 'block';
        
        let contextClient = userClientName;
        if(userRole === 'Admin') {
            const override = document.getElementById('admin-target-client').value.trim();
            contextClient = override || "All";
        }

        try {
            const response = await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: query, role: userRole, client_name: contextClient })
            });

            const data = await response.json();
            loading.style.display = 'none';

            if(data.error) addMessage("Error: " + data.error, 'bot-msg');
            else addBotMessageWithCitations(data.answer, data.citations, data.stepBackQuery);
        } catch (error) {
            loading.style.display = 'none';
            addMessage("Failed to connect to the server.", 'bot-msg');
        }
    }

    function addMessage(text, className) {
        const chatBox = document.getElementById('chat-box');
        const msgDiv = document.createElement('div');
        msgDiv.className = \`message \${className}\`;
        msgDiv.textContent = text;
        chatBox.insertBefore(msgDiv, document.getElementById('loading'));
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function addBotMessageWithCitations(answer, citations, stepBackQuery) {
        const chatBox = document.getElementById('chat-box');
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message bot-msg';
        
        let htmlContent = \`<div class="answer-text">\${answer.replace(/\\n/g, '<br>')}</div>\`;
        if (citations && citations.length > 0) {
            const uniqueCitations = Array.from(new Set(citations.map(c => c.source + "-" + c.page)))
                                         .map(key => citations.find(c => c.source + "-" + c.page === key));
                                         
            htmlContent += \`<div class="citations"><strong>Supporting References:</strong><ul>\`;
            uniqueCitations.forEach(cit => {
                const safeBbox = cit.bbox ? (typeof cit.bbox === 'string' ? cit.bbox.replace(/'/g, "&#39;").replace(/"/g, "&quot;") : JSON.stringify(cit.bbox).replace(/"/g, "&quot;")) : "";
                const cName = cit.client && cit.client !== "public" ? ' (Client: ' + cit.client + ')' : '';
                const fetchUrl = cit.source && cit.source.startsWith('/api/docs/') ? cit.source : '../' + cit.source.split('/').pop();
                htmlContent += \`<li style="margin-bottom: 5px;">
                    <a onclick="loadAndHighlightPdf('\${fetchUrl}', '\${cit.page}', '\${safeBbox}')">
                        \${cit.source.split('/').pop()} (Page \${cit.page})\${cName}
                    </a>
                </li>\`;
            });
            htmlContent += \`</ul></div>\`;
        }
        msgDiv.innerHTML = htmlContent;
        chatBox.insertBefore(msgDiv, document.getElementById('loading'));
        chatBox.scrollTop = chatBox.scrollHeight;
    }
    async function refreshDirectory() {
        const table = document.getElementById('directory-table');
        const tbody = table.querySelector('tbody');
        tbody.innerHTML = '<tr><td colspan="3">Loading...</td></tr>';
        table.style.display = 'table';
        
        try {
            const response = await fetch('/api/directory');
            const data = await response.json();
            
            tbody.innerHTML = '';
            if (data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3">No documents found.</td></tr>';
            } else {
                data.forEach(item => {
                    const tr = document.createElement('tr');
                    const statusBadge = item.isIndexed 
                        ? '<span class="badge badge-green">Indexed</span>' 
                        : '<span class="badge badge-yellow">Sync Required</span>';
                    
                    const syncBtn = item.isIndexed ? '' : \`<button onclick="syncDocument('\${item.fileKey}')" class="sync-btn">Sync</button>\`;
                    
                    tr.innerHTML = \`
                        <td style="padding: 5px; border-bottom: 1px solid #eee;">\${item.fileKey}</td>
                        <td style="padding: 5px; border-bottom: 1px solid #eee;">\${statusBadge}</td>
                        <td style="padding: 5px; border-bottom: 1px solid #eee; text-align: center;">
                            \${syncBtn}
                            <button onclick="deleteDocument('\${item.fileKey}')" class="delete-btn">Delete</button>
                        </td>
                    \`;
                    tbody.appendChild(tr);
                });
            }
        } catch (e) {
            tbody.innerHTML = '<tr><td colspan="3" style="color:red;">Error loading directory.</td></tr>';
        }
    }

    async function syncDocument(fileKey) {
        const statusEl = document.getElementById('ingest-status');
        statusEl.style.color = 'blue';
        statusEl.textContent = \`Syncing \${fileKey}...\`;
        
        try {
            // 1. Download file from R2 via our proxy
            const response = await fetch(\`/api/docs/\${encodeURIComponent(fileKey)}\`);
            const arrayBuffer = await response.arrayBuffer();
            
            // 2. Parse PDF in browser
            const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
            let blocks = [];
            for (let i = 1; i <= pdf.numPages; i++) {
                const page = await pdf.getPage(i);
                const textContent = await page.getTextContent();
                textContent.items.forEach(item => {
                    if (item.str.trim().length > 5) {
                        blocks.push({ 
                            text: item.str, 
                            page: i, 
                            bbox: [item.transform[4], item.transform[5], item.transform[4] + item.width, item.transform[5] + item.transform[3]] 
                        });
                    }
                });
            }
            
            // 3. Send to Ingest API
            const parts = fileKey.split('/');
            const clientName = parts[0];
            const fileName = parts.slice(1).join('/');
            
            const formData = new FormData();
            formData.append('pdfFile', new Blob([arrayBuffer], { type: 'application/pdf' }), fileName);
            formData.append('fileName', fileName);
            formData.append('clientName', clientName);
            formData.append('blocks', JSON.stringify(blocks));

            const ingestRes = await fetch('/api/ingest', { method: 'POST', body: formData });
            const data = await ingestRes.json();
            
            if (data.success) {
                statusEl.style.color = 'green';
                statusEl.textContent = \`Successfully synced \${fileKey}!\`;
                refreshDirectory();
            } else {
                throw new Error(data.error);
            }
        } catch (e) {
            statusEl.style.color = 'red';
            statusEl.textContent = 'Sync failed: ' + e.message;
        }
    }


    async function deleteDocument(fileKey) {
        if (!confirm(\`Are you sure you want to delete \${fileKey}? This will also purge its vector embeddings.\`)) return;
        
        const statusEl = document.getElementById('ingest-status');
        statusEl.style.color = 'blue';
        statusEl.textContent = 'Deleting document and purge vectors...';
        
        try {
            const response = await fetch('/api/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ fileKey })
            });
            const data = await response.json();
            if (data.success) {
                statusEl.style.color = 'green';
                statusEl.textContent = 'Successfully deleted ' + fileKey;
                refreshDirectory();
            } else {
                statusEl.style.color = 'red';
                statusEl.textContent = 'Delete error: ' + data.error;
            }
        } catch (e) {
            statusEl.style.color = 'red';
            statusEl.textContent = 'Failed to delete.';
        }
    }
</script>

</body>
</html>`;

export default {
    async fetch(request, env) {
        const url = new URL(request.url);
        
        if (request.method === "OPTIONS") { return new Response(null, { headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type" } }); }
        
        if (url.pathname === "/") { return new Response(htmlContent, { headers: { "Content-Type": "text/html" } }); }
        
        if (url.pathname === "/api/chat" && request.method === "POST") { return await handleChat(request, env); }
        if (url.pathname === "/api/ingest" && request.method === "POST") { return await handleIngest(request, env); }
        if (url.pathname === "/api/directory" && request.method === "GET") { return await handleDirectory(request, env); }
        if (url.pathname === "/api/delete" && request.method === "POST") { return await handleDelete(request, env); }
        if (url.pathname.startsWith("/api/docs/") && request.method === "GET") { return await handleDocs(request, env); }
        if (url.pathname === "/api/force-alert" && request.method === "POST") { 
            await checkR2StorageSize(env, true);
            return new Response(JSON.stringify({success: true, message: "Alert triggered forcefully"}), { 
                headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" } 
            }); 
        }
        
        return new Response("Not found", { status: 404 });
    },
    async scheduled(event, env, ctx) {
        ctx.waitUntil(checkR2StorageSize(env, false));
    }
}

async function checkR2StorageSize(env, forceAlert = false) {
    let totalBytes = 0;
    let cursor = undefined;
    try {
        do {
            const objects = await env.DOCUMENT_BUCKET.list({ cursor });
            objects.objects.forEach(obj => {
                totalBytes += obj.size;
            });
            cursor = objects.truncated ? objects.cursor : undefined;
        } while (cursor);
        
        const gb = totalBytes / (1024 * 1024 * 1024);
        
        if (gb > 9.5 || forceAlert) {
            const msg = forceAlert 
                ? `[TEST ALERT] Triple A Chatbot Document Storage is currently at ${gb.toFixed(4)} GB.` 
                : `WARNING: Triple A Chatbot Document Storage is at ${gb.toFixed(4)} GB, extremely close to the 10GB free tier limit! Please upgrade or delete files.`;
            
            const tgUrl = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`;
            await fetch(tgUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text: msg })
            });
        }
    } catch (e) {
        console.error("Scheduled task error:", e);
    }
}

async function handleIngest(request, env) {
    try {
        const formData = await request.formData();
        const pdfFile = formData.get('pdfFile');
        const fileName = formData.get('fileName');
        const clientName = formData.get('clientName');
        const blocksStr = formData.get('blocks');

        if(!pdfFile || !blocksStr) return Response.json({error: "Missing file or blocks"}, {status: 400});
        
        const blocks = JSON.parse(blocksStr);
        
        // R2 Upload
        const fileKey = `${clientName}/${fileName}`;
        // Duplicate guard – reject if already present in KV
const existing = await env.VECTOR_MAP.get(fileKey);
if (existing) {
    return Response.json({error: "File already exists"}, {status: 409, headers: {"Access-Control-Allow-Origin": "*"}});
}
await env.DOCUMENT_BUCKET.put(fileKey, pdfFile);
        const stableSourceUrl = `/api/docs/${fileKey}`;

        
        // Very basic sentence chunking to merge blocks into ~200 word chunks
        let chunks = [];
        let currentText = "";
        let currentBbox = null;
        let currentPage = 1;
        
        for(let block of blocks) {
            currentText += block.text + " ";
            if(!currentBbox) { currentBbox = block.bbox; currentPage = block.page; }
            
            // Emit chunk
            if(currentText.split(" ").length > 150) {
                chunks.push({ text: currentText.trim(), bbox: currentBbox, page: currentPage });
                currentText = "";
                currentBbox = null;
            }
        }
        if(currentText.length > 10) chunks.push({ text: currentText.trim(), bbox: currentBbox, page: currentPage });
        
        // Fetch embeddings
        const openaiUrl = "https://api.openai.com/v1/embeddings";
        // Max vector array push is usually 1-3MB, we slice into batches of 100
        let embeddedChunks = [];
        for(let i = 0; i < chunks.length; i += 100) {
            const batch = chunks.slice(i, i+100);
            const inputTexts = batch.map(c => c.text);
            const embedReq = await fetch(openaiUrl, {
                method: "POST",
                headers: { "Authorization": `Bearer ${env.OPENAI_API_KEY}`, "Content-Type": "application/json" },
                body: JSON.stringify({ input: inputTexts, model: "text-embedding-3-small" })
            });
            if(!embedReq.ok) throw new Error("OpenAI error: " + await embedReq.text());
            const res = await embedReq.json();
            for(let j = 0; j < batch.length; j++) {
                embeddedChunks.push({
                    id: crypto.randomUUID().replace(/-/g, ""),
                    values: res.data[j].embedding,
                    metadata: {
                        text: batch[j].text,
                        child_match_text: batch[j].text,
                        source_url: stableSourceUrl,
                        page: batch[j].page,
                        client_name: clientName || "public",
                        bbox: JSON.stringify(batch[j].bbox)
                    }
                });
            }
        }
        
        // For vectorize, insert max 500 at a time
        for(let i = 0; i < embeddedChunks.length; i += 500) {
            const batch = embeddedChunks.slice(i, i+500);
            await env.VECTORIZE.insert(batch);
        }
        
        // Store vector IDs mapping for later deletion
        const vectorIds = embeddedChunks.map(v => v.id);
        await env.VECTOR_MAP.put(fileKey, JSON.stringify(vectorIds));
        return Response.json({ success: true, nodesInserted: embeddedChunks.length }, { headers: { "Access-Control-Allow-Origin": "*" } });
    } catch(e) {
        return Response.json({ error: e.message }, { status: 500, headers: { "Access-Control-Allow-Origin": "*" } });
    }
}
async function handleDirectory(request, env) {
    try {
        const list = await env.DOCUMENT_BUCKET.list();
        const files = list.objects.map(o => ({
            fileKey: o.key,
            size: o.size,
            uploaded: o.uploaded
        })).filter(o => !o.fileKey.startsWith('trash/'));
        
        // Add indexing status from KV
        const enrichedFiles = [];
        for (const file of files) {
            const vectorIds = await env.VECTOR_MAP.get(file.fileKey);
            enrichedFiles.push({ ...file, isIndexed: !!vectorIds });
        }
        
        return Response.json(enrichedFiles, { headers: { "Access-Control-Allow-Origin": "*" } });
    } catch (e) {
        return Response.json({ error: e.message }, { status: 500, headers: { "Access-Control-Allow-Origin": "*" } });
    }
}

async function handleDelete(request, env) {
    try {
        const { fileKey } = await request.json();
        if (!fileKey) return Response.json({ error: "fileKey is required" }, { status: 400, headers: { "Access-Control-Allow-Origin": "*" } });

        // 1. Get vector IDs from KV
        const idsJson = await env.VECTOR_MAP.get(fileKey);
        if (idsJson) {
            const ids = JSON.parse(idsJson);
            // 2. Cascade delete vectors in chunks of 500 (Vectorize limit is usually 1000 per request)
            for (let i = 0; i < ids.length; i += 500) {
                const chunk = ids.slice(i, i + 500);
                await env.VECTORIZE.delete(chunk);
            }
            // 3. Remove KV mapping
            await env.VECTOR_MAP.delete(fileKey);
        }

        // 4. Move R2 object to trash instead of direct deletion
        const obj = await env.DOCUMENT_BUCKET.get(fileKey);
        if (obj) {
            await env.DOCUMENT_BUCKET.put(`trash/${fileKey}`, obj.body, {
                httpMetadata: obj.httpMetadata,
                customMetadata: obj.customMetadata
            });
            await env.DOCUMENT_BUCKET.delete(fileKey);
        }

        return Response.json({ success: true }, { headers: { "Access-Control-Allow-Origin": "*" } });
    } catch (e) {
        return Response.json({ error: e.message }, { status: 500, headers: { "Access-Control-Allow-Origin": "*" } });
    }
}

async function handleChat(request, env) {
    try {
        const body = await request.json();
        const { query, role, client_name } = body;
        if (!query) return Response.json({ error: "Query is required" }, { status: 400 });

        const stepBackReq = await fetch("https://api.openai.com/v1/chat/completions", {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${env.OPENAI_API_KEY}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                model: "gpt-4o",
                messages: [
                    { role: "system", content: "You are an expert at information retrieval. Given a specific user query, write a more abstract, broader question that encompasses the background concepts. Only respond with the question itself." },
                    { role: "user", content: query }
                ],
                temperature: 0.1
            })
        });
        
        let stepBackQuery = "";
        if (stepBackReq.ok) {
            const sbJson = await stepBackReq.json();
            stepBackQuery = sbJson.choices[0].message.content.replace(/["']/g, '');
        }

        const embedReqPayloads = [query];
        if (stepBackQuery) embedReqPayloads.push(stepBackQuery);

        const embedReq = await fetch("https://api.openai.com/v1/embeddings", {
            method: "POST",
            headers: { "Authorization": `Bearer ${env.OPENAI_API_KEY}`, "Content-Type": "application/json" },
            body: JSON.stringify({ input: embedReqPayloads, model: "text-embedding-3-small" })
        });
        
        if (!embedReq.ok) throw new Error("Failed to interact with OpenAI embeddings");
        
        const embedRes = await embedReq.json();
        const primaryVector = embedRes.data[0].embedding;
        const stepBackVector = embedReqPayloads.length > 1 ? embedRes.data[1].embedding : null;

        // Apply metadata filtering constraints based on Role!
        let queryOptions = { topK: 3, returnMetadata: "all" };
        if (role === 'Client') {
            // Client can only see their own documents
            // We use a complex Vectorize query filter if available: metadata.client_name == request client_name
            if (client_name) {
                // Warning: Cloudflare vectorize uses {"client_name": "name"} for eq filter
                queryOptions.filter = { "client_name": client_name };
            }
        } else if (role === 'Admin' && client_name && client_name !== "All") {
            queryOptions.filter = { "client_name": client_name };
        }

        console.log(`[CHAT DIAG] Query: "${query}", Role: ${role}, Client: ${client_name}`);
        console.log(`[CHAT DIAG] Query Options: ${JSON.stringify(queryOptions)}`);

        const vResults1 = env.VECTORIZE.query(primaryVector, queryOptions);
        const sbOptions = { ...queryOptions, topK: 2 };
        const vResults2 = stepBackVector ? env.VECTORIZE.query(stepBackVector, sbOptions) : Promise.resolve({ matches: [] });
        
        const [results1, results2] = await Promise.all([vResults1, vResults2]);
        console.log(`[CHAT DIAG] Primary Matches: ${results1.matches?.length || 0}`);
        console.log(`[CHAT DIAG] StepBack Matches: ${results2.matches?.length || 0}`);
        
        const combinedMatchesMap = new Map();
        (results1.matches || []).forEach(m => combinedMatchesMap.set(m.id, m));
        (results2.matches || []).forEach(m => combinedMatchesMap.set(m.id, m));
        
        const uniqueMatches = Array.from(combinedMatchesMap.values());

        if (uniqueMatches.length === 0) {
            return Response.json({ answer: "I could not find any relevant information in your assigned documents.", citations: [], stepBackQuery }, { headers: { "Access-Control-Allow-Origin": "*" } });
        }

        let contextText = "";
        let citations = [];
        let uniqueContexts = new Set();
        
        uniqueMatches.forEach((res, i) => {
            const meta = res.metadata || {};
            const textToInject = meta.text || "";
            
            if (!uniqueContexts.has(textToInject) && textToInject.trim().length > 0) {
                uniqueContexts.add(textToInject);
                contextText += `--- Document ${uniqueContexts.size} ---\\n${textToInject}\\n\\n`;
            }
            
            citations.push({ 
                source: meta.source_url || "Unknown", 
                client: meta.client_name || "public",
                page: meta.page || 1,
                bbox: meta.bbox || null
            });
        });

        const systemPrompt = `You are an expert AI assistant providing financial information.
        Answer the user's query utilizing ONLY the provided document context below. 
        Even if the context only contains partial or incomplete information related to the query, MUST provide what is available and DO NOT decline to answer. 
        Synthesize whatever details you can find in the context. Only if the context is completely empty or completely unrelated should you state that the documents do not hold the information.
        
        CONTEXT:
        ${contextText}`;

        const chatReq = await fetch("https://api.openai.com/v1/chat/completions", {
            method: "POST",
            headers: { "Authorization": `Bearer ${env.OPENAI_API_KEY}`, "Content-Type": "application/json" },
            body: JSON.stringify({
                model: "gpt-4o",
                messages: [
                    { role: "system", content: systemPrompt },
                    { role: "user", content: query }
                ],
                temperature: 0.0
            })
        });

        if (!chatReq.ok) throw new Error("Failed to chat");

        const chatRes = await chatReq.json();
        const answer = chatRes.choices[0].message.content;

        return Response.json({ answer, citations, stepBackQuery }, { headers: { "Access-Control-Allow-Origin": "*" } });

    } catch (e) {
        return Response.json({ error: e.message }, { status: 500, headers: { "Access-Control-Allow-Origin": "*" } });
    }
}

async function handleDocs(request, env) {
    const url = new URL(request.url);
    const pathMatch = url.pathname.match(/\/api\/docs\/(.*)/);
    if (!pathMatch) return new Response("Not found", { status: 404 });
    
    const fileKey = decodeURIComponent(pathMatch[1]);
    const obj = await env.DOCUMENT_BUCKET.get(fileKey);
    if (!obj) return new Response("Document not found", { status: 404 });
    
    const headers = new Headers();
    headers.set("Content-Type", "application/pdf");
    obj.writeHttpMetadata(headers);
    headers.set("etag", obj.httpEtag);
    
    return new Response(obj.body, { headers });
}
