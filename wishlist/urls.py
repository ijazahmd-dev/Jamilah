
from django.urls import path
from . import views









urlpatterns = [
    path('', views.wishlist_view, name='wishlist'),
    path('add/<int:product_id>/', views.add_to_wishlist, name='add_to_wishlist'),
    path('remove/<int:item_id>/', views.remove_from_wishlist, name='remove_from_wishlist'),
    path('move_to_cart/<int:item_id>/', views.move_to_cart, name='move_to_cart'),
    path('clear/', views.clear_wishlist, name='clear_wishlist'),
    path('move-all-to-cart/', views.move_all_to_cart, name='move_all_to_cart'),
]
