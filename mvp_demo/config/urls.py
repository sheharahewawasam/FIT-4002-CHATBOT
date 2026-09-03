"""URL configuration for the chatbot project."""
import os

from django.contrib import admin
from django.http import FileResponse
from django.urls import path

from rag_api.documents import (
    delete_document,
    document_status,
    list_documents,
    upload_document,
)
from rag_api.users import get_funds, get_users
from rag_api.views import chat_with_advisor_bot


def serve_index(request):
    html_path = os.path.join(os.path.dirname(__file__), '..', 'index.html')
    return FileResponse(open(os.path.abspath(html_path), 'rb'), content_type='text/html')


urlpatterns = [
    path('', serve_index, name='index'),
    path('admin/', admin.site.urls),

    path('api/chat/', chat_with_advisor_bot, name='chat_with_advisor_bot'),

    path('api/documents/', list_documents, name='list_documents'),
    path('api/documents/upload/', upload_document, name='upload_document'),
    path('api/documents/<int:doc_id>/', document_status, name='document_status'),
    path('api/documents/<int:doc_id>/delete/', delete_document, name='delete_document'),

    path('users/', get_users),
    path('users/<str:name>/', get_funds),
]
