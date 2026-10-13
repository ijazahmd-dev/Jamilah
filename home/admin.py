from django.contrib import admin
from .models import SisterhoodSubscriber


@admin.register(SisterhoodSubscriber)
class SisterhoodSubscriberAdmin(admin.ModelAdmin):
    list_display = ('email', 'subscribed_at', 'is_active', 'welcome_email_sent')
    list_filter = ('is_active', 'welcome_email_sent', 'subscribed_at')
    search_fields = ('email',)
    ordering = ('-subscribed_at',)
