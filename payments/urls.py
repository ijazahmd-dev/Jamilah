from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('initiate/', views.initiate_payment, name='initiate_payment'),
    path('verify/<str:order_id>/', views.verify_payment, name='verify_payment'),
    path('success/<str:order_id>/', views.payment_success, name='payment_success'),
    path('failure/<str:order_id>/', views.payment_failure, name='payment_failure'),
    path('retry/<str:order_id>/', views.retry_payment, name='retry_payment'),
    path('retry/confirm/<str:order_id>/', views.retry_order_confirm, name='retry_order_confirm'),
]