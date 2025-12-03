"""
URL configuration for Bluetooth API endpoints.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('health', views.health, name='health'),
    path('register-device', views.register_device, name='register_device'),
    path('check-in', views.check_in, name='check_in'),
    path('nfc-tap', views.nfc_tap, name='nfc_tap'),
    path('scanner/device-detected', views.device_detected, name='device_detected'),
    path('my-status', views.my_status, name='my_status'),
    # Analytics endpoints
    path('analytics/stats', views.analytics_stats, name='analytics_stats'),
    path('analytics/charts', views.analytics_charts, name='analytics_charts'),
    path('analytics/chart/<str:chart_type>', views.analytics_chart, name='analytics_chart'),
]
