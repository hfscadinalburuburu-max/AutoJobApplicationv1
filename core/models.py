from django.db import models

class JobApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('applied', 'Applied'),
        ('interview', 'Interviewing'),
        ('rejected', 'Rejected'),
        ('no_response', 'No Response'),
        ('offer', 'Offer'),
    ]

    company = models.CharField(max_length=255)
    position = models.CharField(max_length=255)
    recruiter_email = models.EmailField(blank=True, null=True)
    intro_name = models.CharField(max_length=100, blank=True, null=True)
    job_link = models.URLField(blank=True, null=True, max_length=1000)
    job_description = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    generated_email = models.TextField(blank=True, null=True)
    date_applied = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    source = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.company} - {self.position}"

    class Meta:
        ordering = ['-created_at']

class JobDiscoveryResult(models.Model):
    company = models.CharField(max_length=255)
    position = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, null=True)
    salary = models.CharField(max_length=255, blank=True, null=True)
    link = models.URLField(blank=True, null=True, max_length=1000)
    source = models.CharField(max_length=50) # indeed, google, linkedin
    snippet = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.position} at {self.company} ({self.source})"

    class Meta:
        ordering = ['-created_at']
