from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from organizations.models import Organization
from .models import User
from .serializers import LoginSerializer, UserProfileSerializer

UNIFORM_AUTH_ERROR = {"error": "Invalid credentials."}


class LoginRateThrottle(AnonRateThrottle):
    """Strict rate limiter against credential stuffing and brute-force attacks."""
    scope = "auth_login"


class LoginView(APIView):
    """
    Session login endpoint. Authenticates an organization-scoped user
    and establishes a hardened session cookie.

    Hardened against user/organization enumeration and timing attacks:
    all authentication failures return an identical HTTP 401 response
    after performing password hashing work.
    """
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        slug = (serializer.validated_data.get("organization_slug") or "").strip().lower()

        if slug:
            organization = Organization.objects.filter(slug=slug, is_active=True).first()
        else:
            # Optional slug: resolve only if email uniquely identifies a single active org
            matching_orgs = list(
                Organization.objects.filter(
                    is_active=True,
                    users__email__iexact=email.strip().lower(),
                    users__is_active=True,
                ).distinct()[:2]
            )
            organization = matching_orgs[0] if len(matching_orgs) == 1 else None

        if organization is None:
            # Constant-time defense: perform dummy password hash to match real failure latency
            User().set_password(password)
            return Response(UNIFORM_AUTH_ERROR, status=status.HTTP_401_UNAUTHORIZED)

        user = authenticate(
            request,
            organization=organization,
            email=email,
            password=password,
        )

        if not user or not user.is_active:
            return Response(UNIFORM_AUTH_ERROR, status=status.HTTP_401_UNAUTHORIZED)

        login(request, user)
        return Response(UserProfileSerializer(user).data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    Terminates the current session and flushes session state.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CurrentUserView(APIView):
    """
    Returns the authenticated user's profile and accessible branches.
    Also ensures the CSRF cookie is set on the client for subsequent requests.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication credentials were not provided."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(UserProfileSerializer(request.user).data, status=status.HTTP_200_OK)
