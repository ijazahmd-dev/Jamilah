from django.contrib import admin
from django.urls import path,include
from . import views




urlpatterns = [
    path('', views.HomePage, name='home'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('contact_success/', views.contact_success, name='contact_success'),
    path('sisterhood/subscribe/', views.sisterhood_subscribe, name='sisterhood_subscribe'),
]
   
    
