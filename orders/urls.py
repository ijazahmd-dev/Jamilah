from django.urls import path
from . import views 



urlpatterns = [
    path('checkout/', views.place_order, name='place_order'),
    path('orders/order-success/<str:order_id>/', views.order_success, name='order_success'),
    path('my-orders/', views.user_orders, name='user_orders'),
    path('my-orders/<str:order_id>/items/', views.order_items, name='order_items'),
    path('my-orders/<str:item_id>/', views.user_order_details, name='user_order_details'),
    path('cancel-order-item/<str:item_id>/', views.cancel_order_item, name='cancel_order_item'),
    path('request-return/<str:item_id>/', views.request_return, name='request_return'),
    path('download-invoice/<str:order_id>/', views.download_invoice, name='download_invoice'),
    path('admin/orders/', views.order_management, name='order_management'),
    path('admin/orders/<str:order_id>/', views.admin_order_details, name='admin_order_details'),
    path('admin/orders/<str:order_id>/update-status/', views.update_order_status, name='update_order_status'),





    
]