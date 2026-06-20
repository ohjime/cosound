"""URLconf for the admin subdomain (admin.cosound.ca).

Mounts the Django admin at the site root so the admin lives at
``admin.cosound.ca/`` instead of ``admin.cosound.ca/admin/``. Selected per
request by ``config.middleware.AdminSubdomainURLConf`` based on the Host
header; the default ``config.urls`` (admin at ``/admin/``) is untouched, so
local dev and the apex/www site are unaffected.
"""

from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("", admin.site.urls),
]
