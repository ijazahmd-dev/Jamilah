from django.db import models

# Create your models here.

class Category(models.Model):
    category_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_listed = models.BooleanField(default=False)
    image = models.ImageField(upload_to='category_images/', blank=True, null=True)
    

    def __str__(self):
        return self.category_name

    
