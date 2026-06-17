from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse, FileResponse
from django.views.static import serve
from pathlib import Path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Auth
    path('api/auth/', include('users.urls')),
    path('api/auth/login/', TokenObtainPairView.as_view(), name='token-obtain-pair'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    # Subjects + Topics + Questions (CRUD)
    path('api/', include('subjects.urls')),
    # Tests
    path('api/tests/', include('tests.urls')),
    # Dashboard
    path('api/dashboard/', include('dashboard.urls')),
]

# Media файлы — в dev через Django
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


# SPA catch-all — в продакшене раздаёт index.html для всех не-API запросов
def spa_catch_all(request):
    """Раздаёт index.html React SPA для всех не-API, не-static, не-media запросов."""
    index_path = Path(settings.STATIC_ROOT) / 'index.html'
    if index_path.exists():
        return FileResponse(open(index_path, 'rb'), content_type='text/html')
    return HttpResponse(
        'Frontend не собран. Запусти: cd frontend && npm run build',
        status=503,
    )


if not settings.DEBUG:
    # Подключаем catch-all только в продакшене
    # Добавляем в самый конец, чтобы не перехватывал API/static/media
    urlpatterns += [path('<path:url>', spa_catch_all)]
