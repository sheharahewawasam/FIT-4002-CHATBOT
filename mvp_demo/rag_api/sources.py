"""
Serving the source documents a citation points at.

The citation links in the chat panel used to be plain relative hrefs -
`../<filename>` - which only ever worked when index.html was opened straight off
someone's filesystem. Served by Django there is no such route, so every link
returned 404.

A filename cannot simply become a URL, because the filename arrives from
Pinecone metadata and the whole point of the access filter is that an advisor
reaches only their own funds' documents. A route that took a filename would let
any signed-in advisor fetch any fund's deed by asking for it by name - exactly
the hole that permitted_funds() closes on the query side.

So the link carries a signed grant instead. The chat view already knows, at the
moment it builds a citation, both the filename and the advisor it is answering;
it signs that pair, and this module will only serve a file whose grant verifies
and whose advisor matches the caller. Nothing derived from the URL reaches the
filesystem unverified, and a link one advisor receives is useless to another.
"""
import logging
import os

from django.conf import settings
from django.core import signing
from django.http import FileResponse, JsonResponse
from rest_framework.decorators import api_view

from .models import Document

logger = logging.getLogger(__name__)

# Grants expire so a link pasted into a ticket or a chat log does not stay live
# indefinitely. Long enough to reopen a document while still reading the answer.
GRANT_MAX_AGE_SECONDS = int(os.getenv("SOURCE_GRANT_MAX_AGE", str(12 * 60 * 60)))

_SALT = "rag_api.sources.grant"


def _roots():
    """
    Directories that may be searched for a bulk-ingested document.

    The sample PDFs sit at the repository root and in pdfs/. Real fund documents
    are deliberately not in version control, so a deployment points
    SOURCE_DOCUMENT_DIRS at wherever they actually live on that host.
    """
    configured = os.getenv("SOURCE_DOCUMENT_DIRS", "")
    dirs = [d.strip() for d in configured.split(os.pathsep) if d.strip()]
    if not dirs:
        project = os.path.dirname(settings.BASE_DIR)
        dirs = [project, os.path.join(project, "pdfs")]
    return [os.path.realpath(d) for d in dirs if os.path.isdir(d)]


def grant_for(filename, advisor_name):
    """
    A signed token naming one file and the advisor allowed to fetch it.

    Returned with the citation, so the browser never has to be trusted with a
    filename that the server would then take at face value.
    """
    if not filename or not advisor_name:
        return None
    return signing.dumps({"f": filename, "u": advisor_name}, salt=_SALT)


def _resolve(filename, advisor):
    """
    Locate the file on disk, or return None.

    An uploaded document is stored under a generated name, so it is found through
    its Document row; a bulk-ingested one is found by basename under the allowed
    roots. Either way the final path is checked to sit inside a directory we
    meant to serve, which is what stops a crafted name escaping - belt and braces
    behind the signature, which already fixes the name.
    """
    base = os.path.basename(filename)
    if not base or base in (".", ".."):
        return None

    doc = (Document.objects
           .filter(owner=advisor, original_filename=base)
           .order_by("-uploaded_at")
           .first())
    if doc and doc.stored_path and os.path.isfile(doc.stored_path):
        uploads = os.path.realpath(os.path.join(settings.MEDIA_ROOT, "uploads"))
        candidate = os.path.realpath(doc.stored_path)
        if os.path.commonpath([uploads, candidate]) == uploads:
            return candidate

    for root in _roots():
        candidate = os.path.realpath(os.path.join(root, base))
        if os.path.commonpath([root, candidate]) != root:
            continue
        if os.path.isfile(candidate):
            return candidate
    return None


@api_view(["GET"])
def serve_source_document(request):
    """
    Return the PDF a citation refers to, for the advisor the link was issued to.

    Every refusal answers the same way as a missing file. Distinguishing "not
    yours" from "does not exist" would tell a caller which documents other funds
    hold, which is the thing the access filter exists to prevent.
    """
    advisor = getattr(request.user, "advisor", None)
    if advisor is None:
        return JsonResponse({"error": "This account is not set up as an advisor."}, status=403)

    token = request.query_params.get("d", "")
    try:
        payload = signing.loads(token, salt=_SALT, max_age=GRANT_MAX_AGE_SECONDS)
    except signing.SignatureExpired:
        return JsonResponse(
            {"error": "This link has expired. Ask the question again to get a fresh one."},
            status=403)
    except signing.BadSignature:
        logger.warning("Bad source-document grant presented by %r", advisor.name)
        return JsonResponse({"error": "Document not found."}, status=404)

    if payload.get("u") != advisor.name:
        # A grant issued to somebody else. Not an error the holder should be able
        # to tell apart from a missing file.
        logger.warning("Advisor %r presented a grant issued to %r",
                       advisor.name, payload.get("u"))
        return JsonResponse({"error": "Document not found."}, status=404)

    path = _resolve(payload.get("f", ""), advisor)
    if path is None:
        # Common and legitimate: the fund documents are not in version control,
        # so a deployment that has not been given them cannot serve them.
        return JsonResponse(
            {"error": "That document is not stored on this server.",
             "filename": os.path.basename(payload.get("f", "")) or None},
            status=404)

    response = FileResponse(open(path, "rb"), content_type="application/pdf")
    # inline so the browser's viewer opens it rather than downloading; the
    # filename is the original one, not the generated storage name.
    response["Content-Disposition"] = (
        f'inline; filename="{os.path.basename(payload["f"])}"')
    return response
