
from django.urls import path
from . import views









urlpatterns = [
    path('cart/', views.cart_view, name='cart_view'),
    path('cart/add/', views.add_to_cart, name='add_to_cart'),
    path('update_cart/<int:item_id>/<str:action>/', views.update_cart, name='update_cart'),
    path('remove_from_cart/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('clear/', views.clear_cart, name='clear_cart'),
    path('move_to_wishlist/<int:item_id>/', views.move_to_wishlist, name='cart_move_to_wishlist'),
    







    # path('add/', views.add_to_cart, name='add_to_cart'),
    # # path('add/<int:product_id>/<int:variant_id>/', views.add_to_cart, name='add_to_cart_variant'),
    # path('update/<int:product_id>/<int:variant_id>/', views.update_cart, name='update_cart'),
    # path('update/<int:product_id>/', views.update_cart, name='update_cart_without_variant'),  # If no variant In cart/urls.py
    

    # # path('update-cart/<int:product_id>/<int:variant_id>/', views.update_cart, name='update_cart'),
    # # path('update-cart/<int:product_id>/', views.update_cart, name='update_cart_without_variant'),
    
    # path('remove/<int:product_id>/<int:variant_id>/', views.remove_from_cart, name='remove_from_cart'),
    # path('remove/<int:product_id>/', views.remove_from_cart, name='remove_from_cart_without_variant'),



    # path('add/<int:product_id>/', views.add_wish_to_cart, name='add_wish_to_cart'),
    # path('add/<int:product_id>/<int:variant_id>/', views.add_wish_to_cart, name='add_wish_to_cart_variant'),

]