from django.contrib import admin
from .models import JobApplication, JobDiscoveryResult

@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ('company', 'position', 'status', 'date_applied', 'created_at')
    list_filter = ('status', 'source')
    search_fields = ('company', 'position', 'notes')

@admin.register(JobDiscoveryResult)
class JobDiscoveryResultAdmin(admin.ModelAdmin):
    list_display = ('company', 'position', 'source', 'processed', 'created_at')
    list_filter = ('source', 'processed')
    search_fields = ('company', 'position')
