from django.db import models
from django.contrib.auth.models import User
from products.models import ProductVariant

class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Cart of {self.user.username if self.user else "Guest"}'


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f'{self.quantity} x {self.product_variant.product.name} ({self.product_variant.color}, {self.product_variant.size})'

    def total_price(self):
        product = self.product_variant.product
        price = product.offer if product.offer else product.price
        return self.quantity * price

    

