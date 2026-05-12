"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

# from rag_api.views import chat_with_advisor_bot
# from rag_api.views_s3 import chat_with_advisor_bot as chat_with_advisor_bot_s3
from rag_api.views_opensearch import chat_with_advisor_bot as chat_with_advisor_bot_opensearch
# from rag_api.views_pinecone import chat_with_advisor_bot as chat_with_advisor_bot_pinecone


urlpatterns = [
    path('admin/', admin.site.urls),
    # Cloudflare
    # path('api/chat/', chat_with_advisor_bot, name='chat_with_advisor_bot'),
    # Amazon S3 Vector
    # path('api/chat/', chat_with_advisor_bot_s3, name='chat_with_advisor_bot_s3'),
    # Amazon OpenSearch Service
    path('api/chat/', chat_with_advisor_bot_opensearch, name='chat_with_advisor_bot_opensearch'),
    # Pinecone
    # path('api/chat/', chat_with_advisor_bot_pinecone, name='chat_with_advisor_bot_pinecone'),
]
