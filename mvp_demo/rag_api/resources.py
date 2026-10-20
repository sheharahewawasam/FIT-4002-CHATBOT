"""
Shared, expensive-to-create resources: the Pinecone index handle, the BGE
embedder, the cross-encoder reranker and the fitted BM25 encoder.

These are module-level singletons so the query path (views.py) and the
ingestion path (ingestion.py) share one copy. Loading them per-module would
roughly double resident memory, which matters on a small VM.
"""
import os

from dotenv import load_dotenv
from pinecone import Pinecone
from pinecone_text.sparse import BM25Encoder
from sentence_transformers import SentenceTransformer, CrossEncoder

_HERE = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(_HERE, "..", "secrets.env"))

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

BM25_ENCODER_PATH = os.getenv(
    "BM25_ENCODER_PATH",
    os.path.join(_HERE, "..", "bm25_encoder.json"),
)

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

# Fitted during bulk ingest. A loaded encoder can still encode new documents,
# so uploads reuse it rather than refitting; terms unique to newly uploaded
# documents carry no IDF weight until the next full refit via ingest.py.
bm25 = BM25Encoder().load(BM25_ENCODER_PATH)

embedder = SentenceTransformer("BAAI/bge-base-en-v1.5")
embedder.max_seq_length = 512

reranker = CrossEncoder("BAAI/bge-reranker-base", max_length=512)

# BGE retrieval quality depends on this prefix being applied to queries only.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
