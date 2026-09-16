"""URLconf for the admin subdomain (admin.cosound.ca).

Mounts the Django admin at the site root so the admin lives at
``admin.cosound.ca/`` instead of ``admin.cosound.ca/admin/``. Selected per
request by ``config.middleware.AdminSubdomainURLConf`` based on the Host
header; the default ``config.urls`` (admin at ``/admin/``) is untouched, so
local dev and the apex/www site are unaffected.

``upload/`` is included because django-file-form builds its upload forms by
reversing ``s3_upload``/``tus_upload``, and reverse() resolves against the
per-request urlconf rather than ROOT_URLCONF. Without these routes every admin
page carrying a file-form field — Sound, Player Program — raises NoReverseMatch
on this host, and the browser would have nowhere to send the upload anyway. It
precedes the admin because ``admin.site.urls`` ends in a catch-all pattern that
would otherwise swallow these paths.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("upload/", include("config.file_upload_urls")),
    path("", admin.site.urls),
]
