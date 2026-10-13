from django.db import models
from category.models import Category
from django.db.models import Avg, Count

class Product(models.Model):
    name = models.CharField(max_length=500)
    description = models.TextField(default = "No description available")
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=7, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    is_listed = models.BooleanField(default=False)

    def __str__(self):
        return self.name
    
    @property
    def best_offer_price(self):
        product_offer = None
        if hasattr(self, 'product_offer'):
            product_offer = self.product_offer if self.product_offer.is_active else None

        category_offer = None
        if hasattr(self.category, 'category_offer'):
            category_offer = self.category.category_offer if self.category.category_offer.is_active else None

        offers = []
        if product_offer:
            offers.append(product_offer.discount_percentage)
        if category_offer:
            offers.append(category_offer.discount_percentage)

        if offers:
            best_discount = max(offers)
            # Convert self.price to float before multiplication
            return round(float(self.price) * (1 - float(best_discount) / 100), 2)
        return None


    @property
    def has_offer(self):
        return self.best_offer_price is not None
    
    @property
    def best_offer_percentage(self):
        # Check for active product offer
        product_offer = None
        if hasattr(self, 'product_offer'):
            product_offer = self.product_offer if self.product_offer.is_active else None

        # Check for active category offer
        category_offer = None
        if hasattr(self.category, 'category_offer'):
            category_offer = self.category.category_offer if self.category.category_offer.is_active else None

        offers = []
        if product_offer:
            offers.append(product_offer.discount_percentage)
        if category_offer:
            offers.append(category_offer.discount_percentage)

        if offers:
            return int(max(offers))
        return 0


    
    @property
    def average_rating(self):
        return self.review_set.aggregate(Avg('rating'))['rating__avg'] or 0

    @property
    def review_count(self):
        return self.review_set.aggregate(Count('id'))['id__count'] or 0

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/')

    def __str__(self):
        return f"{self.product.name} Image"
    


    

class ProductVariant(models.Model):

    SIZE_CHOICES= [
    ('S','Small'),
    ('M','Medium'),
    ('L','Large'),
    ('XL','Extra Large')
  ]


    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    color = models.CharField(max_length=50,null=True)
    size = models.CharField(max_length=2,choices=SIZE_CHOICES)
    stock = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('product', 'color', 'size')  # Prevent duplicates

    def __str__(self):
        return f"{self.product.name} - {self.color} - {self.size}"