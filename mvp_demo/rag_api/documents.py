"""
Document upload and management endpoints.

Identity is still supplied by the client (an advisor name), matching the
existing /users/ endpoints. That is spoofable and must be replaced by
request.user once authentication lands - the checks below are deliberately
written so that swapping in a real authenticated user touches one line each.
"""
import os
import uuid

from django.conf import settings
from django.http import JsonResponse
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser

from .ingestion import delete_document_vectors, start_ingestion
from .models import Advisor, Document, Fund

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf"}


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


def _resolve_advisor(name):
    """Look up the acting advisor. Replace with request.user once auth exists."""
    if not name:
        return None, JsonResponse({"error": "A user must be selected."}, status=400)
    try:
        return Advisor.objects.get(name=name), None
    except Advisor.DoesNotExist:
        return None, JsonResponse({"error": f"Unknown user '{name}'."}, status=404)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload_document(request):
    advisor, err = _resolve_advisor(request.data.get("user"))
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
    advisor, err = _resolve_advisor(request.query_params.get("user"))
    if err:
        return err
    docs = Document.objects.filter(owner=advisor).select_related("fund")
    return JsonResponse({"documents": [_serialise(d) for d in docs]})


@api_view(["GET"])
def document_status(request, doc_id):
    try:
        doc = Document.objects.select_related("fund", "owner").get(pk=doc_id)
    except Document.DoesNotExist:
        return JsonResponse({"error": "Document not found."}, status=404)
    return JsonResponse({"document": _serialise(doc)})


@api_view(["DELETE"])
def delete_document(request, doc_id):
    advisor, err = _resolve_advisor(request.query_params.get("user"))
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
