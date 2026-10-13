from django.db import models
from django.contrib.auth.models import User
from products.models import Product

"""
WISHLIST
"""
class Wishlist(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Wishlist of {self.user.username}'



"""
WISHLIST ITEMS
"""
class WishlistItem(models.Model):
    wishlist = models.ForeignKey(Wishlist, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.product.name} in {self.wishlist.user.username}\'s wishlist'

    class Meta:
        unique_together = ('wishlist', 'product')  # Prevent duplicate products in the wishlist
        
