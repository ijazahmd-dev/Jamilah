from django.db import models
from products.models import Product
from category.models import Category

# Create your models here.

"""
PRODUCT OFFER
"""
class ProductOffer(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='product_offer')
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.name} - {self.discount_percentage}%"
    




"""
CATEGORY OFFER
"""
class CategoryOffer(models.Model):
    category = models.OneToOneField(Category, on_delete=models.CASCADE, related_name='category_offer')
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.category.category_name} - {self.discount_percentage}%"
     

    


