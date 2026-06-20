"""Host-based URLconf switching.

Lets a subdomain serve a different URL tree without affecting any other host.
Currently used so the admin subdomain serves the Django admin at its root.
Add more hosts here later (e.g. ``api.`` -> an API-only urlconf) following the
same pattern.
"""


class AdminSubdomainURLConf:
    """Serve the Django admin at the root of the ``admin.*`` subdomain.

    When the request Host starts with ``admin.`` (e.g. admin.cosound.ca), swap
    in ``config.urls_admin`` (admin mounted at ``/``) for that request only.
    Every other host — including ``localhost`` under ``make server`` — keeps the
    default ``config.urls``, so local dev and the main site are unchanged.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()
        if host.startswith("admin."):
            request.urlconf = "config.urls_admin"
        return self.get_response(request)
