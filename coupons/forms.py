import re
from django import forms
from django.utils import timezone
from .models import Coupon

class CouponForm(forms.ModelForm):
    error_css_class = 'error'
    required_css_class = 'required'

    class Meta:
        model = Coupon
        fields = [
            'coupon_code', 'description', 'minimum_purchase_amount', 'discount_percentage',
            'max_discount_amount', 'valid_from', 'valid_to'
        ]
        widgets = {
            'valid_from': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'valid_to': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'coupon_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. SUMMER20'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Coupon details'}),
            'minimum_purchase_amount': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'discount_percentage': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '90'}),
            'max_discount_amount': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
        }

    def clean_coupon_code(self):
        coupon_code = self.cleaned_data.get('coupon_code', '').strip().upper()
        if not coupon_code:
            raise forms.ValidationError("Coupon code is required and cannot be empty or spaces.")
        if len(coupon_code) < 3 or len(coupon_code) > 20:
            raise forms.ValidationError("Coupon code must be between 3 and 20 characters.")
        if not re.match(r'^[A-Z0-9_-]+$', coupon_code):
            raise forms.ValidationError("Coupon code can only contain letters, numbers, hyphens, and underscores.")

        qs = Coupon.objects.filter(coupon_code__iexact=coupon_code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A coupon with this code already exists.")

        return coupon_code

    def clean_description(self):
        description = self.cleaned_data.get('description', '').strip()
        if not description:
            raise forms.ValidationError("Description is required and cannot be whitespace only.")
        if len(description) < 5 or len(description) > 500:
            raise forms.ValidationError("Description must be between 5 and 500 characters.")
        return description

    def clean_discount_percentage(self):
        discount_percentage = self.cleaned_data.get('discount_percentage')
        if discount_percentage is None:
            raise forms.ValidationError("Discount percentage is required.")
        if discount_percentage < 1 or discount_percentage > 90:
            raise forms.ValidationError("Discount percentage must be between 1% and 90%.")
        return discount_percentage

    def clean_minimum_purchase_amount(self):
        minimum_purchase_amount = self.cleaned_data.get('minimum_purchase_amount')
        if minimum_purchase_amount is None:
            raise forms.ValidationError("Minimum purchase amount is required.")
        if minimum_purchase_amount < 0:
            raise forms.ValidationError("Minimum purchase amount cannot be negative.")
        if minimum_purchase_amount > 1000000:
            raise forms.ValidationError("Minimum purchase amount cannot exceed ₹1,000,000.")
        return minimum_purchase_amount

    def clean_max_discount_amount(self):
        max_discount_amount = self.cleaned_data.get('max_discount_amount')
        if max_discount_amount is None:
            raise forms.ValidationError("Maximum discount amount is required.")
        if max_discount_amount < 1:
            raise forms.ValidationError("Maximum discount amount must be at least ₹1.")
        if max_discount_amount > 100000:
            raise forms.ValidationError("Maximum discount amount cannot exceed ₹100,000.")
        return max_discount_amount

    def clean(self):
        cleaned_data = super().clean()
        valid_from = cleaned_data.get('valid_from')
        valid_to = cleaned_data.get('valid_to')
        instance = getattr(self, 'instance', None)

        if instance and instance.pk:
            if 'valid_from' in self.changed_data:
                if valid_from and valid_from < timezone.now().date():
                    self.add_error('valid_from', 'Valid from date cannot be in the past.')
            if valid_to and valid_from and valid_to < valid_from:
                self.add_error('valid_to', 'Valid to date cannot be before valid from date.')
        else:
            if valid_from and valid_from < timezone.now().date():
                self.add_error('valid_from', 'Valid from date cannot be in the past.')
            if valid_to and valid_from and valid_to < valid_from:
                self.add_error('valid_to', 'Valid to date cannot be before valid from date.')

        return cleaned_data

                
