"""
Document upload and management endpoints.

Identity comes from the signed-in session. It used to be an advisor name in the
request body, which any caller could set to any value; every endpoint here now
resolves the advisor from request.user instead, and each one scopes its query by
that advisor so a document belonging to somebody else cannot be reached by
guessing its id.
"""
import os
import uuid

from django.conf import settings
from django.http import JsonResponse
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser

from .ingestion import delete_document_vectors, start_ingestion
from .models import Document, Fund

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf"}

# Ingestion is off unless a deployment explicitly turns it on.
#
# The endpoint takes an advisor name from the request body and trusts it, so
# until authentication lands anyone who can reach the server can write into the
# shared Pinecone index. Off by default means a host that is exposed to the
# internet is safe without remembering to configure anything; a developer who
# wants to ingest locally sets DOCUMENT_UPLOADS_ENABLED=true.
UPLOADS_ENABLED = os.getenv("DOCUMENT_UPLOADS_ENABLED", "false").lower() in ("1", "true", "yes")


def _serialise(doc):
    return {
        "id": doc.pk,
        "filename": doc.original_filename,
        "fund": doc.fund.name if doc.fund else None,
        "doc_type": doc.doc_type,
        "status": doc.status,
        "error": doc.error,
        "chunk_count": doc.chunk_count,
        "uploaded_at": doc.uploaded_at.isoformat(),
    }


def _resolve_advisor(request):
    """
    The advisor for the signed-in user.

    IsAuthenticated has already run, so an anonymous caller never arrives here.
    What remains is an auth user with no advisor record, which has no funds and
    therefore no documents.
    """
    advisor = getattr(request.user, "advisor", None)
    if advisor is None:
        return None, JsonResponse(
            {"error": "This account is not set up as an advisor."}, status=403)
    return advisor, None


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload_document(request):
    if not UPLOADS_ENABLED:
        return JsonResponse(
            {"error": "Document uploads are disabled on this server."}, status=403)

    advisor, err = _resolve_advisor(request)
    if err:
        return err

    upload = request.FILES.get("file")
    if not upload:
        return JsonResponse({"error": "No file was provided."}, status=400)

    ext = os.path.splitext(upload.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return JsonResponse({"error": "Only PDF files are supported."}, status=400)
    if upload.size > MAX_UPLOAD_BYTES:
        return JsonResponse(
            {"error": f"File is too large (limit {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)."},
            status=400,
        )

    fund = None
    fund_name = (request.data.get("fund") or "").strip()
    if fund_name:
        fund, _ = Fund.objects.get_or_create(name=fund_name)
        # An advisor can only file a document under a fund they can see.
        if not advisor.funds.filter(pk=fund.pk).exists():
            return JsonResponse(
                {"error": f"'{advisor.name}' does not have access to fund '{fund_name}'."},
                status=403,
            )

    upload_dir = os.path.join(settings.MEDIA_ROOT, "uploads", str(advisor.pk))
    os.makedirs(upload_dir, exist_ok=True)
    # Keep the original name for display but store under a unique one, so two
    # uploads of the same filename cannot overwrite each other.
    stored_path = os.path.join(upload_dir, f"{uuid.uuid4().hex}{ext}")
    with open(stored_path, "wb") as fh:
        for chunk in upload.chunks():
            fh.write(chunk)

    doc = Document.objects.create(
        owner=advisor,
        fund=fund,
        original_filename=upload.name,
        stored_path=stored_path,
        doc_type=(request.data.get("doc_type") or "Uploaded").strip() or "Uploaded",
        status=Document.PENDING,
    )

    # Extraction and embedding can take minutes on a scanned PDF, so the
    # request returns now and the client polls the status endpoint.
    start_ingestion(doc)

    return JsonResponse({"document": _serialise(doc)}, status=202)


@api_view(["GET"])
def list_documents(request):
    advisor, err = _resolve_advisor(request)
    if err:
        return err
    docs = Document.objects.filter(owner=advisor).select_related("fund")
    # The flag travels with the listing so the page hides the upload form on a
    # server that will only reject it. The server still enforces it.
    return JsonResponse({
        "documents": [_serialise(d) for d in docs],
        "uploads_enabled": UPLOADS_ENABLED,
    })


@api_view(["GET"])
def document_status(request, doc_id):
    advisor, err = _resolve_advisor(request)
    if err:
        return err
    try:
        # Scoped by owner: this used to fetch on the id alone, so any signed-in
        # caller could read the filename, fund and progress of anyone's upload
        # by counting upwards. Not found and not yours are the same answer.
        doc = Document.objects.select_related("fund", "owner").get(pk=doc_id, owner=advisor)
    except Document.DoesNotExist:
        return JsonResponse({"error": "Document not found."}, status=404)
    return JsonResponse({"document": _serialise(doc)})


@api_view(["DELETE"])
def delete_document(request, doc_id):
    advisor, err = _resolve_advisor(request)
    if err:
        return err
    try:
        doc = Document.objects.get(pk=doc_id, owner=advisor)
    except Document.DoesNotExist:
        return JsonResponse({"error": "Document not found."}, status=404)

    removed = delete_document_vectors(doc)
    if doc.stored_path and os.path.exists(doc.stored_path):
        try:
            os.remove(doc.stored_path)
        except OSError:
            pass
    doc.delete()
    return JsonResponse({"deleted": True, "vectors_removed": removed})
