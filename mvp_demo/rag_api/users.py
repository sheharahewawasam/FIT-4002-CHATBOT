"""
Fund lookups for the signed-in advisor.

These used to be open: /users/ returned the whole advisor roster and
/users/<name>/ returned any advisor's fund list, which told an anonymous caller
who the clients were and which funds existed. Both now answer only about the
caller.

The endpoints are kept rather than deleted because the page and the tests still
call them; /api/auth/me/ returns the same facts alongside the identity.
"""
from django.http import JsonResponse
from rest_framework.decorators import api_view


def _advisor(request):
    return getattr(request.user, "advisor", None)


@api_view(['GET'])
def get_users(request):
    """The signed-in advisor, as a one-element list so the shape is unchanged."""
    advisor = _advisor(request)
    return JsonResponse({"users": [advisor.name] if advisor else []})


@api_view(['GET'])
def get_funds(request, name):
    advisor = _advisor(request)
    # Asking about somebody else is answered the same way as asking about a name
    # that does not exist, so the response cannot be used to enumerate advisors.
    if advisor is None or advisor.name != name:
        return JsonResponse({"error": "User not found"}, status=404)
    return JsonResponse({"data": advisor.fund_names()})
