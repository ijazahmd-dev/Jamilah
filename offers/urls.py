from django.urls import path
from . import views 

urlpatterns = [
    path('', views.offer_management, name='offer_management'),
    path('offers/', views.offer_management),
    path('product-offers/', views.product_offer_list, name='product_offer_list'),
    path('product/add-offer/', views.add_product_offer, name='add_product_offer'),
    path('product-offers/add/', views.add_product_offer),
    path('product/<int:product_id>/edit-offer/', views.edit_product_offer, name='edit_product_offer'),
    path('product/<int:product_id>/toggle-offer/', views.toggle_product_offer, name='toggle_product_offer'),
    path('product/<int:product_id>/delete-offer/', views.delete_product_offer, name='delete_product_offer'),
    path('category-offers/', views.category_offer_list, name='category_offer_list'),
    path('category/add-offer/', views.add_category_offer, name='add_category_offer'),
    path('category-offers/add/', views.add_category_offer),
    path('category/<int:category_id>/edit-offer/', views.edit_category_offer, name='edit_category_offer'),
    path('category/<int:category_id>/toggle-offer/', views.toggle_category_offer, name='toggle_category_offer'),
    path('category/<int:category_id>/delete-offer/', views.delete_category_offer, name='delete_category_offer'),
]