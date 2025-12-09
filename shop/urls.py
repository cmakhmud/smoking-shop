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
    
    # Main pages
    path('worker/', views.worker_dashboard, name='worker'),
    path('finance/', views.finance_dashboard, name='finance'),
    path('create-debt/', views.create_debt_page, name='create_debt_page'),
    path('debts/', views.debt_list, name='debt_list'),
    path('worker/open-pack/', views.worker_open_pack, name='worker_open_pack'),
    path('stock-receipt/', views.stock_receipt, name='stock_receipt'),
    
    # API endpoints for sales
    path('api/search/', views.search_goods, name='search_goods'),
    path('api/scan/', views.scan_barcode, name='scan_barcode'),
    path('api/sale/', views.process_sale, name='process_sale'),
    
    # API endpoints for debt management
    path('api/debt/create/', views.create_debt, name='create_debt'),
    path('api/debt/pay/', views.pay_debt, name='pay_debt'),
    path('api/debt/cancel/', views.cancel_debt, name='cancel_debt'),
    
    # API endpoints for pack opening
    path('api/open-pack/', views.api_open_pack, name='api_open_pack'),
    
    # API endpoints for stock receipt
    path('api/stock-receipt/', views.api_stock_receipt, name='api_stock_receipt'),
    
    # NEW URLs for stock management scanning (finds goods even with 0 stock)
    path('api/scan-stock/', views.scan_barcode_for_stock, name='scan_barcode_stock'),
    path('api/search-stock/', views.search_goods_for_stock, name='search_goods_stock'),
    
    # ✅ YENİ ƏLAVƏ EDİLƏN URL-LƏR: Yeni məhsul yaratma və kateqoriyalar
    path('api/create-good/', views.create_good_api, name='create_good_api'),
    path('api/categories/', views.api_categories, name='api_categories'),
    
    # Authentication URLs
    path('login/', auth_views.LoginView.as_view(template_name='shop/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='shop:login'), name='logout'),
]