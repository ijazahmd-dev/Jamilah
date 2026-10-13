
from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static









urlpatterns = [
    
    path("user-profile/",views.user_profile,name='user_profile'),
    path("user-address/", views.view_addresses, name='addresses'),
    path("address/set-default/<int:address_id>/", views.set_default_address, name='set_default_address'),
    path("add-address/",views.add_address, name='add_address'),
    path('edit-address/<int:address_id>/', views.edit_address, name='edit_address'),
    path('delete-address/<int:address_id>/', views.delete_address, name='delete_address'),
    path('change-password/', views.change_password, name='change_password'),
    path('change-email/', views.change_email, name='change_email'),
    path('verify-email/', views.verify_email, name='verify_email'),
    path('update-profile-picture/', views.update_profile_picture, name='update_profile_picture'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


