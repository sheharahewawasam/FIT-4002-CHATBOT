"""
Advisor and fund lookups.

These used to be a hardcoded dict; they now read from the database so that
uploaded documents can be related to an advisor. Identity is still supplied by
the client and is therefore not a security boundary - see documents.py.
"""
from django.http import JsonResponse
from rest_framework.decorators import api_view

from .models import Advisor


@api_view(['GET'])
def get_users(request):
    return JsonResponse({"users": list(Advisor.objects.values_list("name", flat=True))})


@api_view(['GET'])
def get_funds(request, name):
    try:
        advisor = Advisor.objects.get(name=name)
    except Advisor.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({"data": advisor.fund_names()})
