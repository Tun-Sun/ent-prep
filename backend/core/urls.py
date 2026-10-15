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
    # Gamification (achievements, duels)
    path('api/gamification/', include('gamification.urls')),
    # Оцифровка новых книг (загрузил PDF -> черновики в банке)
    path('api/ingest/', include('ingest.urls')),
]


_index_html = Path(settings.STATIC_ROOT) / 'index.html'
_frontend_ready = _index_html.exists()


def _serve_frontend(request):
    if not _frontend_ready:
        return HttpResponse(
            'Frontend не собран. Запусти: cd frontend && npm run build',
            status=503,
        )
    response = FileResponse(open(_index_html, 'rb'), content_type='text/html')
    _allow_getcourse_frame(request, response)
    return response


def _allow_getcourse_frame(request, response):
    """Разрешить встраивание платформы в урок GetCourse (Шаг 6.1).

    Оболочка урока живёт на домене GetCourse, а страница задания — у нас, поэтому
    обычный `X-Frame-Options: DENY` оставлял бы ученика в пустом фрейме. Право
    встроить отдаём списку доменов из `.env` и только этим путям: на остальном
    фрейме (админка, API) заголовок продолжает стоять как стоял.

    `xframe_options_exempt` — штатный способ сказать промежуточному слою заголовка
    не ставить; вместо него работает `frame-ancestors`, который современными
    браузерами читается, а старым просто не понятен (и тогда фрейм молча не
    откроется, а не откроется у кого попало).
    """
    if not settings.GC_FRAME_ANCESTORS:
        return
    path = request.path
    if not any(path == p or path.startswith(p.rstrip('/') + '/') for p in settings.GC_FRAME_PATHS):
        return
    response.xframe_options_exempt = True
    response['Content-Security-Policy'] = 'frame-ancestors \'self\' %s' % ' '.join(
        settings.GC_FRAME_ANCESTORS)


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
urlpatterns.insert(0, re_path(r'^(?!/?(?:api|admin|grappelli|media|static|assets)/).*$', _serve_frontend))
