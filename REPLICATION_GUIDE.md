# Replication Guide: Triple A Super Advisor Chatbot

This guide provides a comprehensive step-by-step process to replicate the Triple A Super Advisor Chatbot. By following these steps, you will achieve the same retrieval-augmented generation (RAG) results as the current implementation.

---

## 🏗️ Architecture Overview

The chatbot uses a modern AI stack:
- **Frontend**: Vanilla HTML/JavaScript (MVP).
- **Backend**: Django REST Framework (Python).
- **Embeddings**: OpenAI `text-embedding-3-small`.
- **Vector Database**: Cloudflare Vectorize.
- **LLM**: OpenAI `gpt-4o`.
- **Ingestion**: LlamaIndex for hierarchical chunking and parent-retrieval.

---

## 🛠️ Phase 1: Prerequisites & Account Setup

Before you start, ensure you have the following:

1.  **OpenAI Account**: 
    - Obtain an [OpenAI API Key](https://platform.openai.com/).
    - Ensure you have credits (GPT-4o and Embeddings require a paid tier).
2.  **Cloudflare Account**:
    - Sign up for [Cloudflare](https://dash.cloudflare.com/).
    - You need access to **Vectorize** (available on the Free/Paid Workers plans).
3.  **Python 3.10+**: Make sure Python is installed on your machine.

---

## 📂 Phase 2: Local Environment Setup

1.  **Clone the Repository**:
    ```bash
    git clone <repository-url>
    cd FIT-4002-CHATBOT
    ```

2.  **Create a Virtual Environment**:
    ```bash
    cd mvp_demo
    python -m venv venv
    source venv/bin/activate  # Windows: .\venv\Scripts\activate
    ```

3.  **Install Dependencies**:
    Ensure you install both the core requirements and the LlamaIndex components.
    ```bash
    pip install django djangorestframework django-cors-headers requests pypdf openai python-dotenv llama-index-core
    ```

4.  **Configure Environment Variables**:
    Create a `.env` file in the `mvp_demo` directory:
    ```env
    # OpenAI
    OPENAI_API_KEY=your_openai_key

    # Cloudflare
    CLOUDFLARE_ACCOUNT_ID=your_account_id
    CLOUDFLARE_API_TOKEN=your_token_with_vectorize_edit_permissions
    CLOUDFLARE_VECTORIZE_INDEX=triple_a_index
    ```

---

## ☁️ Phase 3: Cloudflare Vectorize Configuration

You must create a vector index in Cloudflare before ingesting data.

1.  **Install Wrangler (Optional, for CLI)**:
    ```bash
    npm install -g wrangler
    wrangler login
    ```

2.  **Create the Index**:
    Run the following command to create an index compatible with OpenAI's `text-embedding-3-small` (1536 dimensions):
    ```bash
    wrangler vectorize create triple_a_index --dimensions=1536 --metric=cosine
    ```
    *Alternatively, create it via the Cloudflare Dashboard under "Workers & Pages" > "Vectorize".*

---

## 📥 Phase 4: Data Ingestion

The chatbot's "intelligence" comes from the ingested documents.

1.  **Prepare PDF Files**:
    Place the following files in the root `FIT-4002-CHATBOT/` directory:
    - `Project_26.pdf`
    - `Proposal Document.pdf`
    - `Trust_Deed_Sample_Superannuation_Fund.pdf`

2.  **Run the Ingestion Script**:
    This script will:
    - Parse the PDFs using `pypdf`.
    - Perform hierarchical chunking (creating parent and child nodes) via `LlamaIndex`.
    - Generate OpenAI embeddings.
    - Upload vectors and metadata to Cloudflare Vectorize.
    ```bash
    python ingest.py
    ```

---

## 🚀 Phase 5: Running the System

1.  **Start the Backend**:
    From the `mvp_demo` directory:
    ```bash
    python manage.py migrate  # Only needed once
    python manage.py runserver
    ```
    The API will be available at `http://127.0.0.1:8000`.

2.  **Access the Frontend**:
    Open `index.html` in your web browser. 
    *Note: If you encounter CORS issues, ensure `CORS_ALLOW_ALL_ORIGINS = True` is set in `mvp_demo/config/settings.py`.*

---

## 🔍 Troubleshooting

- **No answers?** Check if `ingest.py` finished successfully and that your `CLOUDFLARE_VECTORIZE_INDEX` name matches in both Cloudflare and your `.env`.
- **401 Unauthorized?** Ensure your Cloudflare API Token has the `Vectorize: Edit` permission.
- **Missing LlamaIndex modules?** If `ingest.py` fails on imports, run `pip install llama-index-core`.


