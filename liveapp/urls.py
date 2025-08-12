from django.http import HttpResponse
from django.urls import path
from django.conf.urls.static import static
from django.conf import settings
from . import views

urlpatterns = [
    # Dashboard chính
    path('dashboard/', views.monitor_dashboard, name='dashboard'),
    
    # API endpoints
    path('api/start/', views.start_monitor, name='start_monitor'),
    path('api/stop/', views.stop_monitor, name='stop_monitor'),
    path('api/status/', views.get_monitor_status, name='monitor_status'),
    
    # Stream logs real-time
    path('logs/<str:username>/', views.stream_logs, name='stream_logs'),
    
    # Serve audio files
    path('audio/<str:filename>/', views.serve_audio, name='serve_audio'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
