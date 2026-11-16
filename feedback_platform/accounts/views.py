from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from organizations.models import Organization
from .serializers import LoginSerializer, UserProfileSerializer


class LoginView(APIView):
    """
    Session login endpoint. Authenticates an organization-scoped user
    and establishes a secure session cookie.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        slug = serializer.validated_data["organization_slug"].strip().lower()

        try:
            organization = Organization.objects.get(slug=slug, is_active=True)
        except Organization.DoesNotExist:
            return Response(
                {"error": "Organization not found or inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(
            request,
            organization=organization,
            email=email,
            password=password,
        )

        if not user:
            return Response(
                {"error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"error": "User account is deactivated."},
                status=status.HTTP_403_FORBIDDEN,
            )

        login(request, user)
        return Response(UserProfileSerializer(user).data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    Terminates the current session and clears session cookies.
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
