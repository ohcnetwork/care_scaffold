from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from __PLUGIN_SNAKE__.settings import plugin_settings


class ConfigView(APIView):
    """Client-safe configuration, so the frontend hardcodes nothing.

    Only expose values that are safe in a browser. Never return API secrets.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "enabled": plugin_settings.__PLUGIN_PREFIX___ENABLED,
            }
        )
