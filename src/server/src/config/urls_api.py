"""URLconf for the API subdomain (api.cosound.ca).

Mounts the django-ninja API at the site root so endpoints live at
``api.cosound.ca/<endpoint>`` instead of ``cosound.ca/api/<endpoint>``. Selected
per request by ``config.middleware.SubdomainURLConf`` based on the Host header;
the default ``config.urls`` (API at ``/api/``) is untouched, so local dev and
the apex/www site are unaffected.
"""

from django.urls import path

from app.api import api_urls

urlpatterns = [
    path("", api_urls),
]
