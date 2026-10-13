from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

# Create your models here.


class Coupon(models.Model):
    coupon_id = models.BigAutoField(primary_key=True)
    coupon_code = models.CharField(max_length=50, unique=True)
    minimum_purchase_amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    max_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=200)
    valid_from = models.DateField()
    valid_to = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.coupon_code

    

    def is_valid(self):
        now = timezone.now().date()
        return self.valid_from <= now <= self.valid_to and self.is_active

    @property
    def status_label(self):
        now = timezone.now().date()
        if not self.is_active:
            return 'Inactive'
        if self.valid_to < now:
            return 'Expired'
        if self.valid_from > now:
            return 'Upcoming'
        return 'Active'

    @property
    def is_expired(self):
        return self.valid_to < timezone.now().date()
    



class CouponUsage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'coupon')

    def __str__(self):
        return f"{self.user.username} used {self.coupon.coupon_code}"
    
    
