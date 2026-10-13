"""
URL configuration for mainproject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('', include('home.urls')),
    path('admin/', admin.site.urls),
    path('user/', include('registration.urls')),
    path('accounts/', include('allauth.urls')),
    path('adminpanel/', include('admin_side.urls')),
    path('category/', include('category.urls')),
    path('products/', include('products.urls')),
    path('shop/', include('shop.urls')),
    path('wallet/', include('wallet.urls')),
    path('cart/', include('cart.urls')),
    path('wishlist/', include('wishlist.urls')),
    path('', include('user_profile.urls')),
    path('orders/', include('orders.urls')),
    path('payments/', include('payments.urls')),
    path('coupons/', include('coupons.urls')),
    path('offers/', include('offers.urls')),
    path('review/', include('reviews.urls')),
    path('login/', include('registration.urls')),
    
    
]



urlpatterns += static(settings.STATIC_URL, document_root = settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root = settings.MEDIA_ROOT)


