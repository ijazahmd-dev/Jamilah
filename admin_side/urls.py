from django.contrib import admin
from django.urls import path,include
from . import views


urlpatterns = [
    path('adminlogin/', views.admin_login, name='admin_login'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('sales_report/', views.generate_sales_report, name='generate_sales_report'),
    path('users/',views.user_manage,name='users'),
    path('users/block/<int:user_id>/', views.block_user, name='block_user'),
    path('users/unblock/<int:user_id>/', views.unblock_user, name='unblock_user'),
    path('logout/', views.admin_logout, name='logout'),



    
    
]