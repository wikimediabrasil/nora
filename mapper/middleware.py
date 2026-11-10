class SecurityHeadersMiddleware:
    """Restricts where page scripts can send data: NORA itself, HTTPS sites, or a local model."""

    POLICY = "connect-src 'self' https: http://localhost:* http://127.0.0.1:*"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.POLICY)
        return response
