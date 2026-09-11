"""URL routes.

Core mounts this module at /api/__PLUGIN_SNAKE__/ via the PLUGIN_APPS loop in
config/urls.py. Do not repeat that prefix here.

Routes under `otp/` are for the patient portal (OTP-authenticated, phone-number scoped).
Keep them read-mostly. See the care-auth-contexts skill.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from __PLUGIN_SNAKE__.viewsets.config import ConfigView

router = DefaultRouter()
# router.register("things", ThingViewSet, basename="__PLUGIN_ROUTE__-thing")
# router.register("otp/things", OTPThingViewSet, basename="otp-__PLUGIN_ROUTE__-thing")

urlpatterns = [
    *router.urls,
    path("config/", ConfigView.as_view(), name="__PLUGIN_SNAKE__-config"),
]
