from django.db import models
from products.models import Product
from django.contrib.auth.models import User
from orders.models import OrderItem

# Create your models here.

"""
REVIEW
"""
class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)])
    review_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'product')

    def __str__(self):
        return f"Review by {self.user.username} for {self.product.name}"

    @classmethod
    def can_review(cls, user, product):
        return OrderItem.objects.filter(
            order__user=user,
            product=product,
            status='delivered'
        ).exists()

