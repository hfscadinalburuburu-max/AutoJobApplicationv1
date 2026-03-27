from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='index'),
    path('add/', views.AddJobView.as_view(), name='add_job'),
    path('discovery/', views.DiscoveryView.as_view(), name='discovery'),
    path('settings/', views.SettingsView.as_view(), name='settings'),
    
    # API endpoints for AJAX
    path('api/fetch-jd/', views.fetch_jd_api, name='api_fetch_jd'),
    path('api/generate-email/', views.generate_email_api, name='api_generate_email'),
    path('api/send-email/', views.send_email_api, name='api_send_email'),
    path('api/update-status/<int:pk>/', views.update_status_api, name='api_update_status'),
]
