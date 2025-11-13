from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'shop'

urlpatterns = [
    path('worker/', views.worker_dashboard, name='worker'),
    path('api/scan/', views.scan_barcode, name='scan_barcode'),
    path('api/sale/', views.process_sale, name='process_sale'),
    path('finance/', views.finance_dashboard, name='finance'),
    
    # Add authentication URLs
    path('login/', auth_views.LoginView.as_view(template_name='shop/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='shop:login'), name='logout'),
]
