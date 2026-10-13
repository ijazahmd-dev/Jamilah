from django.urls import path
from . import views 



urlpatterns = [
    path('coupons/', views.view_coupons, name='view_coupons'),
    path('apply-coupon/', views.apply_coupon, name='apply_coupon'),
    path('remove-coupon/', views.remove_coupon, name='remove_coupon'),
    path('admin/coupons/', views.coupon_list, name='coupon_list'),
    path('admin/coupons/add',views.add_coupon, name='add_coupon'),
    path('admin/coupons/edit/<int:coupon_id>/', views.edit_coupon, name='edit_coupon'),
    path('admin/coupons/toggle-status/<int:coupon_id>/', views.toggle_coupon_status, name='toggle_coupon_status'),
    path('admin/coupons/delete/<int:coupon_id>/', views.delete_coupon, name='delete_coupon'),

   
    
]