"""
Sign-in, sign-out, and "who am I".

Session-based: the browser holds a cookie, the server holds the session. That
suits this deployment - nginx serves the page and the API from one origin - and
means no token sits in JavaScript for an XSS to steal.

Because these are the only endpoints an anonymous caller may reach, each one
that needs to be public says so explicitly with AllowAny. Everything else in the
project is closed by the DEFAULT_PERMISSION_CLASSES in settings.py.
"""
import logging

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle

logger = logging.getLogger(__name__)


class LoginRateThrottle(AnonRateThrottle):
    """Rate limit sign-in attempts so the form cannot be used to guess passwords."""
    scope = "login"


def describe(user):
    """What the page needs to render itself for a signed-in advisor."""
    advisor = getattr(user, "advisor", None)
    return {
        "username": user.username,
        "advisor": advisor.name if advisor else None,
        "funds": advisor.fund_names() if advisor else [],
        "is_staff": user.is_staff,
    }


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def login_view(request):
    username = (request.data.get("username") or "").strip().lower()
    password = request.data.get("password") or ""

    if not username or not password:
        return JsonResponse({"error": "Enter a username and password."}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is None:
        # One message for both a wrong name and a wrong password: saying which
        # was wrong tells an attacker which usernames exist.
        logger.info("Failed sign-in for %r", username)
        return JsonResponse({"error": "Incorrect username or password."}, status=401)

    if not hasattr(user, "advisor"):
        # An auth user with no advisor record has no funds, so there is nothing
        # for them to ask about. Refuse rather than sign them into an empty app.
        logger.warning("User %r signed in with no advisor record", username)
        return JsonResponse(
            {"error": "This account is not set up as an advisor. Contact an administrator."},
            status=403)

    # Rotates the session key, so a session id captured before sign-in is useless.
    login(request, user)
    request.session["active"] = True
    return JsonResponse({"user": describe(user)})


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return JsonResponse({"ok": True})


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def whoami(request):
    """
    Lets the page decide whether to show the login form or the chat.

    Open to anonymous callers on purpose: the answer for one is simply
    authenticated=false. It also plants the CSRF cookie the login POST needs.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False})
    return JsonResponse({"authenticated": True, "user": describe(request.user)})
