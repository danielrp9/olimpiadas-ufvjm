from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('users.urls')),
    path('', include('core.urls')),
]

# Adiciona o reload apenas se estiver nas apps instaladas
if 'django_browser_reload' in settings.INSTALLED_APPS:
    urlpatterns += [path('__reload__/', include('django_browser_reload.urls'))]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
