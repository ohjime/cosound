from django.core.mail import EmailMultiAlternatives
from django_tasks import task


@task()
def send_auth_email_task(subject, body, to_email, html_content=None):
    email = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=None,  # Uses DEFAULT_FROM_EMAIL
        to=[to_email],
    )
    if html_content:
        email.attach_alternative(html_content, "text/html")
    email.send()
