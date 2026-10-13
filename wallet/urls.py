

from django.contrib import admin
from django.urls import path
from . import views









urlpatterns = [
    path("", views.wallet_view, name='wallet_view'),
    path("topup/initiate/", views.initiate_wallet_topup, name='initiate_wallet_topup'),
    path("topup/verify/", views.verify_wallet_topup, name='verify_wallet_topup'),
    path("admin/transactions/", views.admin_wallet_transaction_list, name='admin_wallet_transaction_list'),
    path("admin/transaction/<str:transaction_id>/", views.admin_wallet_transaction_detail, name='admin_wallet_transaction_detail'),
]