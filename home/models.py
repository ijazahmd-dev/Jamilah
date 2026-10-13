from django.db import models


class SisterhoodSubscriber(models.Model):
    email = models.EmailField(unique=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    welcome_email_sent = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Sisterhood Subscriber"
        verbose_name_plural = "Sisterhood Subscribers"
        ordering = ['-subscribed_at']

    def __str__(self):
        return self.email
