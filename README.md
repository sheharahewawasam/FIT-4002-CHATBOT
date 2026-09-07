# FIT-4002-CHATBOT

## How to run it locally

1. `cd mvp_demo`
2. Create and activate a virtualenv, then install deps:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt python-dotenv pinecone pinecone-text
   ```
   (`pinecone`, `pinecone-text`, and `python-dotenv` are required by `rag_api/views.py` but not listed in `requirements.txt`.)
3. Copy `.env` to `secrets.env` — the code loads `secrets.env`, not `.env`:
   ```
   cp .env secrets.env
   ```
   Required keys: `OPENAI_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_VECTORIZE_INDEX`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`. Keys are in the shared folder in the API keys folder.
4. Install and start Ollama, then pull the models used in `rag_api/views.py`:
   ```
   ollama serve &
   ollama pull qwen3
   ollama pull jina/jina-embeddings-v2-base-en
   ```
5. Run migrations and start the server:
   ```
   python manage.py migrate
   python manage.py runserver
   ```
6. Open http://127.0.0.1:8000/ for the chat UI, or POST to `/api/chat/` with `{"query": "...", "funds": [...]}`.

## Common Issues

1. no env file, keys should be in the shared folder in the api keys folder
2. Make sure your env file is named secrets.env or you can change the call to the name in ingest.py and views.py, up2u

## Ollama guide

1. Install Ollama
2. Pull wjatever the models used in views.py into ollama

## PaddleOCR Guide

1. Install PaddlePaddle framework

```
python -m pip install paddlepaddle==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
```

2. Install PaddleOCR

```
python -m pip install paddleocr[all]
```

## Pinecone Guide

1. Install Pinecone

```
pip install pinecone
```

2. Install BM25

```
pip install pinecone-text
```


# Run Grader.py
0. Run the thing first/ make sure its working (ollama is pulled etc)
1. cd into mvp_demo
2. python -u ragmetrics\Grader.py *> log.txt
3. look it log.txt as the results populate