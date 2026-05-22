const htmlContent = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Advisor RAG Chatbot MVP</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; margin: 0; padding: 20px; display: flex; justify-content: center; }
        .chat-container { width: 100%; max-width: 600px; background: white; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); display: flex; flex-direction: column; height: 80vh; }
        .header { background: #0056b3; color: white; padding: 15px; border-radius: 10px 10px 0 0; text-align: center; }
        .chat-box { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 15px; }
        .message { max-width: 80%; padding: 12px; border-radius: 8px; line-height: 1.4; }
        .user-msg { background: #e1f5fe; align-self: flex-end; border: 1px solid #b3e5fc; }
        .bot-msg { background: #f5f5f5; align-self: flex-start; border: 1px solid #e0e0e0; }
        .citations { font-size: 0.8em; color: #555; margin-top: 8px; padding-top: 8px; border-top: 1px solid #ddd; }
        .citations a { color: #0056b3; text-decoration: none; }
        .input-area { display: flex; padding: 15px; border-top: 1px solid #ddd; background: #fff; border-radius: 0 0 10px 10px; }
        input[type="text"] { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 5px; margin-right: 10px; outline: none; }
        button { padding: 10px 20px; background: #0056b3; color: white; border: none; border-radius: 5px; cursor: pointer; transition: 0.3s; }
        button:hover { background: #004494; }
        .loading { align-self: flex-start; color: #888; font-style: italic; display: none; }
    </style>
</head>
<body>

<div class="chat-container">
    <div class="header">
        <h2>Triple A Super Advisor AI</h2>
    </div>
    <div class="chat-box" id="chat-box">
        <div class="message bot-msg">Hello. I am the internal RAG assistant. Ask me a question about our project documents.</div>
        <div class="loading" id="loading">Searching knowledge base...</div>
    </div>
    <div class="input-area">
        <input type="text" id="query-input" placeholder="e.g., What is the purpose of the RAG chatbot?" onkeypress="handleKeyPress(event)">
        <button onclick="sendQuery()">Ask</button>
    </div>
</div>

<script>
    const API_URL = '/api/chat'; 

    function handleKeyPress(e) {
        if(e.key === 'Enter') sendQuery();
    }

    async function sendQuery() {
        const inputField = document.getElementById('query-input');
        const query = inputField.value.trim();
        if(!query) return;

        addMessage(query, 'user-msg');
        inputField.value = '';
        
        const loading = document.getElementById('loading');
        loading.style.display = 'block';

        try {
            const response = await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: query })
            });

            const data = await response.json();
            loading.style.display = 'none';

            if(data.error) {
                addMessage("Error: " + data.error, 'bot-msg');
            } else {
                addBotMessageWithCitations(data.answer, data.citations, data.stepBackQuery);
            }
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

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function addBotMessageWithCitations(answer, citations, stepBackQuery) {
        const chatBox = document.getElementById('chat-box');
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message bot-msg';

        let htmlContent = \`<div class="answer-text">\${escapeHtml(answer).replace(/\\n/g, '<br>')}</div>\`;

        // Add step back debug text to prove the optimization strategy works
        if (stepBackQuery) {
             htmlContent += \`<div style="font-size:0.75em; color: green; margin-top: 10px;">[Optimized Search included Step-Back concept: "\${escapeHtml(stepBackQuery)}"]</div>\`;
        }

        if (citations && citations.length > 0) {
            const uniqueCitations = Array.from(new Set(citations.map(c => c.source)))
                                         .map(src => citations.find(c => c.source === src));

            htmlContent += \`<div class="citations"><strong>Sources:</strong><ul>\`;
            uniqueCitations.forEach(cit => {
                const filename = escapeHtml(cit.source.split('/').pop());
                const fund     = escapeHtml(cit.fund);
                const type     = escapeHtml(cit.type);
                htmlContent += \`<li><a href="../\${filename}" target="_blank" style="color:#0056b3;">\${filename}</a> (\${fund} - \${type})</li>\`;
            });
            htmlContent += \`</ul></div>\`;
        }

        msgDiv.innerHTML = htmlContent;
        chatBox.insertBefore(msgDiv, document.getElementById('loading'));
        chatBox.scrollTop = chatBox.scrollHeight;
    }
</script>

</body>
</html>`;

export default {
    async fetch(request, env) {
        const url = new URL(request.url);
        
        // CORS preflight
        if (request.method === "OPTIONS") {
            return new Response(null, { 
                headers: { 
                    "Access-Control-Allow-Origin": "*", 
                    "Access-Control-Allow-Headers": "Content-Type" 
                } 
            });
        }
        
        // HTML Frontend Route
        if (url.pathname === "/") {
            return new Response(htmlContent, { 
                headers: { "Content-Type": "text/html" } 
            });
        }
        
        // API Route
        if (url.pathname === "/api/chat" && request.method === "POST") {
            return await handleChat(request, env);
        }
        
        return new Response("Not found", { status: 404 });
    }
}

async function handleChat(request, env) {
    try {
        const body = await request.json();
        const query = body.query;
        if (!query) return Response.json({ error: "Query is required" }, { status: 400 });

        // Phase 1: Query Optimization -> Step-Back Prompting
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

        // Phase 2: Embed BOTH queries concurrently for multi-query Hybrid retrieval
        const openaiUrl = "https://api.openai.com/v1/embeddings";
        const embedReqPayloads = [query];
        if (stepBackQuery) embedReqPayloads.push(stepBackQuery);

        const embedReq = await fetch(openaiUrl, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${env.OPENAI_API_KEY}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ input: embedReqPayloads, model: "text-embedding-3-small" })
        });
        
        if (!embedReq.ok) {
            throw new Error("Failed to interact with OpenAI: " + await embedReq.text());
        }
        
        const embedRes = await embedReq.json();
        const primaryVector = embedRes.data[0].embedding;
        const stepBackVector = embedReqPayloads.length > 1 ? embedRes.data[1].embedding : null;

        // Phase 3: Query Cloudflare Vectorize (Multi-Query Execution)
        const vResults1 = env.VECTORIZE.query(primaryVector, { topK: 5, returnMetadata: "all" });
        const vResults2 = stepBackVector ? env.VECTORIZE.query(stepBackVector, { topK: 3, returnMetadata: "all" }) : Promise.resolve({ matches: [] });
        
        const [results1, results2] = await Promise.all([vResults1, vResults2]);
        
        // Merge: keep the higher-scoring entry when the same vector ID appears in both queries,
        // then sort descending by score so the LLM receives the most relevant context first.
        const combinedMatchesMap = new Map();
        for (const m of (results1.matches || [])) combinedMatchesMap.set(m.id, m);
        for (const m of (results2.matches || [])) {
            const existing = combinedMatchesMap.get(m.id);
            if (!existing || (m.score || 0) > (existing.score || 0)) combinedMatchesMap.set(m.id, m);
        }
        const uniqueMatches = Array.from(combinedMatchesMap.values())
            .sort((a, b) => (b.score || 0) - (a.score || 0));

        if (uniqueMatches.length === 0) {
            return Response.json({ answer: "I could not find any relevant information in the fund documents to answer your query.", citations: [], stepBackQuery });
        }

        // Phase 4: Construct Hierarchical Linked Context and Citations
        let contextText = "";
        let citations = [];
        let uniqueContexts = new Set();
        
        uniqueMatches.forEach((res, i) => {
            const meta = res.metadata || {};
            const textToInject = meta.text || "";
            
            // Deduplicate overlapping parent chunks
            if (!uniqueContexts.has(textToInject) && textToInject.trim().length > 0) {
                uniqueContexts.add(textToInject);
                contextText += `--- Document ${uniqueContexts.size} ---\n${textToInject}\n\n`;
            }
            
            citations.push({ 
                source: meta.source_url || "Unknown", 
                fund: meta.fund_name || "Unknown",
                type: meta.doc_type || "Document"
            });
        });

        // Phase 5: Generate Answer via LLM
        const systemPrompt = `You are an expert AI assistant providing information to advisors.
        Answer the user's query using the provided document context below. 
        Even if the context only contains partial or incomplete information related to the query, MUST provide what is available and DO NOT decline to answer. 
        Synthesize whatever details you can find in the context. Only if the context is completely empty or completely unrelated should you state that the documents do not hold the information.
        
        CONTEXT:
        ${contextText}`;

        const chatReq = await fetch("https://api.openai.com/v1/chat/completions", {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${env.OPENAI_API_KEY}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                model: "gpt-4o",
                messages: [
                    { role: "system", content: systemPrompt },
                    { role: "user", content: query }
                ],
                temperature: 0.0
            })
        });

        if (!chatReq.ok) {
            throw new Error("Failed to interact with OpenAI Chat: " + await chatReq.text());
        }

        const chatRes = await chatReq.json();
        const answer = chatRes.choices[0].message.content;

        // Return JSON payload
        return Response.json({ answer, citations, stepBackQuery }, {
            headers: { "Access-Control-Allow-Origin": "*" }
        });

    } catch (e) {
        return Response.json({ error: e.message }, { status: 500, headers: { "Access-Control-Allow-Origin": "*" } });
    }
}
