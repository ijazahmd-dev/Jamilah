import re
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.db.models.signals import post_save
from django.dispatch import receiver

# Create your models here.




"""
REFERRAL OPTION
"""
class Referral(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='referral')
    referral_code = models.CharField(max_length=20, unique=True, blank=True)
    referred_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals')

    def save(self, *args, **kwargs):
        if not self.referral_code:
            # Generate a structured referral code (exactly 20 characters)
            date_part = timezone.now().strftime("%Y%m%d")  # Current date in YYYYMMDD format (8 chars)
            raw_name = (self.user.username or self.user.email or "USR").split('@')[0]
            clean_name = re.sub(r'[^A-Za-z0-9]', '', raw_name) or "USR"
            user_part = (clean_name[:3] if len(clean_name) >= 3 else clean_name.ljust(3, 'X')).upper()

            while True:
                random_part = get_random_string(3).upper()  # Random 3-character string
                code = f"REF-{date_part}-{user_part}-{random_part}"
                if not Referral.objects.filter(referral_code=code).exclude(pk=self.pk).exists():
                    self.referral_code = code
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.referral_code}"











"""
ADDRESS
"""
class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50, default='Kerala')
    country = models.CharField(max_length=100, default='India')
    postcode = models.CharField(max_length=20)
    phone = models.CharField(max_length=20)
    is_default = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} \n{self.address}, {self.city} \n{self.state},{self.country},{self.postcode} \nPhone: {self.phone}"
    

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).update(is_default=False)
        super(Address, self).save(*args, **kwargs)

# Ensure there is one default address per user
def set_default_address(sender, instance, **kwargs):
    if instance.is_default:
        Address.objects.filter(user=instance.user).exclude(pk=instance.pk).update(is_default=False)

models.signals.pre_save.connect(set_default_address, sender=Address)


"""
SHIPPING ADDRESS
"""
class ShippingAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shipping_addresses')
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50, default='Kerala')
    country = models.CharField(max_length=100, default='India')
    postcode = models.CharField(max_length=20)
    phone = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.name} \n{self.address}, {self.city} \n{self.state},{self.country},{self.postcode} \nPhone: {self.phone}"









class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    avatar = models.ImageField(upload_to='profile_pictures/', null=True, blank=True)

    def __str__(self):
        return f'{self.user.username} Profile'

# Create Profile, Referral, and Wallet automatically when User is created
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)
        Referral.objects.get_or_create(user=instance)
        try:
            from wallet.models import Wallet
            Wallet.objects.get_or_create(user=instance)
        except Exception:
            pass

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
