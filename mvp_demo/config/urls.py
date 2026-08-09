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
from django.http import FileResponse
import os

from rag_api.views import chat_with_advisor_bot

def serve_index(request):
    html_path = os.path.join(os.path.dirname(__file__), '..', 'index.html')
    return FileResponse(open(os.path.abspath(html_path), 'rb'), content_type='text/html')

urlpatterns = [
    path('', serve_index, name='index'),
    path('admin/', admin.site.urls),
    path('api/chat/', chat_with_advisor_bot, name='chat_with_advisor_bot'),
]
