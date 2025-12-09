"""
URL configuration for async_service project.
"""
from django.contrib import admin
from django.urls import path
from analysis_processor import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/async/process-analysis', views.process_analysis, name='process-analysis'),
]
