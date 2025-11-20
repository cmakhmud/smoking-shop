from django.urls import path
from django.shortcuts import redirect
from . import views
from django.contrib.auth import views as auth_views

app_name = 'shop'

urlpatterns = [
    # Health check endpoint
    path('health/', views.health_check, name='health'),
    
    # Root redirect to login
    path('', lambda request: redirect('shop:login'), name='root_redirect'),
    
    path('worker/', views.worker_dashboard, name='worker'),
    path('api/search/', views.search_goods, name='search_goods'),
    path('api/scan/', views.scan_barcode, name='scan_barcode'),
    path('api/sale/', views.process_sale, name='process_sale'),
    path('finance/', views.finance_dashboard, name='finance'),
    
    path('create-debt/', views.create_debt_page, name='create_debt_page'),
    path('debts/', views.debt_list, name='debt_list'),
    path('api/debt/create/', views.create_debt, name='create_debt'),
    path('api/debt/pay/', views.pay_debt, name='pay_debt'),
    path('api/debt/cancel/', views.cancel_debt, name='cancel_debt'),

    path('worker/open-pack/', views.worker_open_pack, name='worker_open_pack'),
    path('api/open-pack/', views.api_open_pack, name='api_open_pack'),

    # Add authentication URLs
    path('login/', auth_views.LoginView.as_view(template_name='shop/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='shop:login'), name='logout'),
]
