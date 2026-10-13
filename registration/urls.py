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
from . import views

urlpatterns = [
    
    # Registration
    path('signup/',views.SignupPage,name='signup'),
    path('otp/verify/',views.verify_otp,name='verify_otp'),
    path('otp/resend/',views.resend_otp,name='resend_otp'),




    path('',views.LoginPage,name='login'),
    path('logout/',views.User_Logout,name='userlogout'),
    


    # Forgot Password
    
    path('forgot-password/',views.ForgotPassword,name='forgot_password'),
    path('verify-forgot-password-otp/',views.verify_forgot_password_otp,name='verify_forgot_password_otp'),
    path('reset-password/', views.reset_password, name='reset_password'),


    
]
