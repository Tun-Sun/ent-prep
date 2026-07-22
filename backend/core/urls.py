from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse, FileResponse
from django.views.static import serve as static_serve
from pathlib import Path
from rest_framework_simplejwt.views import TokenRefreshView
from users.views import LoginView


urlpatterns = [
    path('grappelli/', include('grappelli.urls')),
    path('admin/', admin.site.urls),
    # Auth
    path('api/auth/', include('users.urls')),
    path('api/auth/login/', LoginView.as_view(), name='token-obtain-pair'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    # Subjects + Topics + Questions (CRUD)
    path('api/', include('subjects.urls')),
    # Tests
    path('api/tests/', include('tests.urls')),
    # Dashboard
    path('api/dashboard/', include('dashboard.urls')),
    # Grant Calculator
    path('api/grant-calc/', include('grant_calc.urls')),
]


_index_html = Path(settings.STATIC_ROOT) / 'index.html'
_frontend_ready = _index_html.exists()


def _serve_frontend(request):
    if _frontend_ready:
        return FileResponse(open(_index_html, 'rb'), content_type='text/html')
    return HttpResponse(
        'Frontend не собран. Запусти: cd frontend && npm run build',
        status=503,
    )


# Медиа-файлы (картинки вопросов) — всегда через Django
# В продакшне на собственном сервере заменить на раздачу через Nginx.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Ассеты фронтенда — раздаём из staticfiles/assets/ по пути /assets/
_assets_root = Path(settings.STATIC_ROOT) / 'assets'
if _assets_root.exists():
    urlpatterns += [
        path('assets/<path:path>', static_serve, {'document_root': str(_assets_root)}),
    ]

# SPA — все пути, кроме api/ admin/ grappelli/ media/ static/ assets/
urlpatterns.insert(0, re_path(r'^(?!(?:api|admin|grappelli|media|static|assets)/).*$', _serve_frontend))
