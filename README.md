# Triple A Chatbot 🤖

A robust RAG-based (Retrieval-Augmented Generation) chatbot system designed for efficient document querying and context-aware responses. Built with Django, integrated with OpenAI for intelligent conversation, and powered by Cloudflare Vectorize for high-performance vector search.

---

## 🚀 Getting Started

For a step-by-step tutorial on how to recreate this entire system from scratch, please refer to the [**Replication Guide**](REPLICATION_GUIDE.md).

### 📋 Prerequisites
- **Python**: Version 3.10 or higher
- **Cloudflare**: Account with Vectorize access
- **OpenAI**: API Key for LLM functionality

### 🔐 Environment Configuration
The application requires several environment variables for API integrations. For security, the `.env` file is ignored by Git.

**Action Required:**
1. Navigate to the `mvp_demo/` directory.
2. Create a file named `.env`.
3. Copy the following template and fill in your credentials:

```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Cloudflare Vectorize Configuration
CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id_here
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token_here
CLOUDFLARE_VECTORIZE_INDEX=your_vector_index_name_here
```

> [!IMPORTANT]
> Never commit your actual `.env` file to the repository. If you need to share a template, use a renamed version like `.env.example` (but ensure it contains no real secrets).

---

## 🛠️ Installation & Setup

### 1. Set up Virtual Environment
```bash
cd mvp_demo
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Initialize Database
```bash
python manage.py migrate
```

### 4. Run the Application
```bash
python manage.py runserver
```

---

## 📂 Project Structure
- `mvp_demo/`: Main application directory.
- `ingest.py`: Script for document ingestion and vectorization.
- `rag_api/`: Django application containing the chatbot logic and API endpoints.
- `cloudflare_demo/`: Experimental work with Cloudflare workers and vectorization.

---

## 🧪 Testing and Ingestion

To ingest new documents into the vector store:
1. Ensure your `.env` is correctly configured.
2. Place relevant documents in the designated path (refer to `ingest.py`).
3. Run the ingestion script:
```bash
python ingest.py
```

---

*Documented by Antigravity*
