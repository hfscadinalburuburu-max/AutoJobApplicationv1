from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, TemplateView
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import json

from core.models import JobApplication, JobDiscoveryResult
import config
from services.ai_generator import generate_email_body, extract_job_details, AIGenerationError
from services.job_discovery import fetch_job_description, search_jobs
from services.email_sender import build_message, send_email

class DashboardView(ListView):
    model = JobApplication
    template_name = 'dashboard/index.html'
    context_object_name = 'applications'

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.GET.get('status')
        search = self.request.GET.get('search')
        
        if status and status != 'All':
            qs = qs.filter(status=status)
        if search:
            qs = qs.filter(company__icontains=search) | qs.filter(position__icontains=search)
            
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stats = {
            'total': JobApplication.objects.count(),
            'applied': JobApplication.objects.filter(status='applied').count(),
            'interview': JobApplication.objects.filter(status='interview').count(),
            'offer': JobApplication.objects.filter(status='offer').count(),
        }
        context['stats'] = stats
        context['statuses'] = JobApplication.STATUS_CHOICES
        context['current_status'] = self.request.GET.get('status', 'All')
        context['search_query'] = self.request.GET.get('search', '')
        return context

class AddJobView(TemplateView):
    template_name = 'dashboard/add_job.html'

class DiscoveryView(TemplateView):
    template_name = 'dashboard/discovery.html'

class SettingsView(TemplateView):
    template_name = 'dashboard/settings.html'

# --- API Endpoints for AJAX ---

@require_POST
def fetch_jd_api(request):
    try:
        data = json.loads(request.body)
        url = data.get('url', '').strip()
        if not url:
            return JsonResponse({'error': 'URL is required'}, status=400)
            
        raw_text = fetch_job_description(url)
        if not raw_text:
            return JsonResponse({'error': 'Could not fetch JD from that URL'}, status=400)
            
        try:
            details = extract_job_details(raw_text)
            return JsonResponse({'success': True, 'details': details, 'raw_text': raw_text})
        except AIGenerationError:
            return JsonResponse({'success': True, 'details': {}, 'raw_text': raw_text, 'warning': 'AI auto-fill failed'})
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_POST
def generate_email_api(request):
    try:
        data = json.loads(request.body)
        company = data.get('company')
        position = data.get('position')
        jd = data.get('job_description')
        
        if not all([company, position, jd]):
            return JsonResponse({'error': 'Company, position, and job description are required'}, status=400)
            
        body, tokens = generate_email_body(company=company, position=position, job_description=jd)
        return JsonResponse({'success': True, 'body': body, 'tokens': tokens})
    except AIGenerationError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_POST
def send_email_api(request):
    try:
        data = json.loads(request.body)
        company = data.get('company')
        position = data.get('position')
        email = data.get('email')
        intro_name = data.get('intro_name', 'Hiring Manager')
        body = data.get('body')
        link = data.get('link', '')
        jd = data.get('jd', '')
        notes = data.get('notes', '')
        
        if not all([company, position, email, body]):
            return JsonResponse({'error': 'Missing required fields to send email'}, status=400)
            
        subject = config.EMAIL_SUBJECT_TEMPLATE.format(position=position, company=company)
        msg = build_message(to=email, intro_name=intro_name, subject=subject, ai_body=body, cv_path=config.CV_PATH)
        
        send_email(msg)
        
        # Save to DB
        from django.utils import timezone
        app = JobApplication.objects.create(
            company=company,
            position=position,
            recruiter_email=email,
            intro_name=intro_name,
            job_link=link,
            job_description=jd,
            notes=notes,
            generated_email=body,
            status='applied',
            source='web_manual',
            date_applied=timezone.now()
        )
        
        return JsonResponse({'success': True, 'id': app.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_POST
def update_status_api(request, pk):
    try:
        data = json.loads(request.body)
        status = data.get('status')
        if not status:
            return JsonResponse({'error': 'Status is required'}, status=400)
            
        app = get_object_or_404(JobApplication, pk=pk)
        app.status = status
        app.save()
        return JsonResponse({'success': True, 'status': status})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
