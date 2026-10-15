from django.urls import path
from recorder import views

urlpatterns = [
    path('api/v1/health/', views.health),
    path('api/v1/targets/', views.targets),
    path('api/v1/targets/<str:username>/', views.targetDetail),
    path('api/v1/targets/<str:username>/start/', views.startTarget),
    path('api/v1/targets/<str:username>/stop/', views.stopTarget),
    path('api/v1/targets/<str:username>/schedule/', views.scheduleTarget),
    path('api/v1/recordings/', views.recordings),
    path('api/v1/recordings/<int:recordingId>/download/', views.downloadRecording),
    path('api/v1/recordings/<int:recordingId>/', views.deleteRecording),
    path('api/v1/recordings/<int:recordingId>/logs/', views.recordingLogs),
    path('api/v1/logs/', views.logs),
    path('api/v1/profile/', views.profile),
]
