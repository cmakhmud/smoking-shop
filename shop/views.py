from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count, Avg, Q ,ExpressionWrapper ,F ,FloatField
from django.contrib import messages
from decimal import Decimal
import json
from django.utils import timezone
from datetime import datetime, time as dt_time ,timedelta
import logging
import pytz
# Add these missing imports
from django.db import connection
from django.contrib.auth.models import User
from django.conf import settings
from .models import Shop, Category, Good, Sale, Expense

logger = logging.getLogger(__name__)

from .models import Shop, Category, Good, Sale

def search_goods(request):
    query = request.GET.get('q', '').strip()
    shop_id = request.GET.get('shop_id')
    
    if not query or not shop_id:
        return JsonResponse({'results': []})
    
    try:
        goods = Good.objects.filter(
            Q(name__icontains=query) | Q(barcode__icontains=query),
            shop_id=shop_id,
            stock_count__gt=0
        )[:10]  # Limit to 10 results
        
        results = []
        for good in goods:
            results.append({
                'id': good.id,
                'name': good.name,
                'price': float(good.price),
                'barcode': good.barcode,
                'category': good.category.name if good.category else '',
                'stock_count': good.stock_count
            })
        
        return JsonResponse({'results': results})
        
    except Exception as e:
        return JsonResponse({'error': 'Axtarış xətası'}, status=500)

def health_check(request):
    try:
        # Test database connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        # Test if auth tables exist
        user_count = User.objects.count()
        
        return JsonResponse({
            'status': 'healthy', 
            'database': 'connected',
            'users_count': user_count,
            'debug': settings.DEBUG  # Use settings.DEBUG instead of DEBUG
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'database': str(e)})

def worker_dashboard(request):
    shops = Shop.objects.all()
    return render(request, 'shop/worker.html', {'shops': shops})


@require_http_methods(["POST"])
def scan_barcode(request):
    data = json.loads(request.body)
    barcode = data.get('barcode', '').strip()
    shop_id = data.get('shop_id')

    if not barcode or not shop_id:
        return JsonResponse({'error': 'Barcode and shop are required'}, status=400)

    try:
        good = Good.objects.select_related('category', 'shop').get(
            barcode=barcode,
            shop_id=shop_id
        )

        if good.stock_count <= 0:
            return JsonResponse({'error': 'Out of stock'}, status=400)

        return JsonResponse({
            'id': good.id,
            'name': good.name,
            'price': str(good.price),
            'category': good.category.name,
            'stock_count': good.stock_count,
            'barcode': good.barcode
        })
    except Good.DoesNotExist:
        return JsonResponse({'error': 'Good not found with this barcode'}, status=404)


@require_http_methods(["POST"])
def process_sale(request):
    data = json.loads(request.body)
    items = data.get('items', [])
    shop_id = data.get('shop_id')

    if not items or not shop_id:
        return JsonResponse({'error': 'Items and shop are required'}, status=400)

    try:
        shop = get_object_or_404(Shop, id=shop_id)
        current_time = datetime.now()  # ← Use datetime.now() for computer local time

        for item in items:
            good = get_object_or_404(Good, id=item['id'], shop=shop)
            quantity = int(item['quantity'])

            if good.stock_count < quantity:
                return JsonResponse({
                    'error': f'Insufficient stock for {good.name}. Available: {good.stock_count}'
                }, status=400)

            good.stock_count -= quantity
            good.save()

            Sale.objects.create(
                good=good,
                quantity=quantity,
                total_price=good.price * quantity,
                shop=shop,
                timestamp=current_time  # ← Use computer local time
            )

        return JsonResponse({'success': True, 'message': 'Sale completed successfully'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def finance_dashboard(request):
    shops = Shop.objects.all()
    categories = Category.objects.all()

    shop_id = request.GET.get('shop')
    category_id = request.GET.get('category')
    barcode = request.GET.get('barcode')
    date_filter = request.GET.get('date_filter', 'today')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    worker_shift = request.GET.get('worker_shift')

    # Handle expense submission
    if request.method == 'POST' and 'expense_amount' in request.POST:
        if not request.user.is_superuser:  # Only workers can add expenses
            try:
                expense_amount = Decimal(request.POST.get('expense_amount'))
                expense_description = request.POST.get('expense_description', '')
                expense_shop_id = request.POST.get('expense_shop')
                
                if expense_amount > 0 and expense_shop_id:
                    Expense.objects.create(
                        shop_id=expense_shop_id,
                        amount=expense_amount,
                        description=expense_description,
                        created_by=request.user,
                        expense_date=timezone.now().date()
                    )
                    messages.success(request, 'Xərc uğurla əlavə edildi!')
            except (ValueError, Decimal.InvalidOperation):
                messages.error(request, 'Xərc məbləği düzgün deyil!')

    sales = Sale.objects.select_related('good', 'shop', 'good__category').all()

    if shop_id:
        sales = sales.filter(shop_id=shop_id)
    if category_id:
        sales = sales.filter(good__category_id=category_id)
    if barcode:
        sales = sales.filter(good__barcode__icontains=barcode)

    # Use Django's timezone system instead of pytz
    now = timezone.now()
    azerbaijan_offset = timedelta(hours=4)
    now_baku = now + azerbaijan_offset
    today_baku = now_baku.date()

    # Date filter
    if date_filter == 'today':
        sales = sales.filter(timestamp__date=today_baku)
    elif date_filter == 'week':
        start_of_week = now_baku - timedelta(days=now_baku.weekday())
        start_of_week_utc = start_of_week - azerbaijan_offset
        sales = sales.filter(timestamp__gte=start_of_week_utc)
    elif date_filter == 'month':
        sales = sales.filter(
            timestamp__year=now_baku.year,
            timestamp__month=now_baku.month
        )
    elif date_filter == 'custom' and start_date and end_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            if not start_time and not end_time:
                sales = sales.filter(timestamp__date__gte=start_date_obj, timestamp__date__lte=end_date_obj)
            else:
                if start_time:
                    start_dt = datetime.combine(start_date_obj, datetime.strptime(start_time, '%H:%M').time())
                else:
                    start_dt = datetime.combine(start_date_obj, dt_time.min)
                
                if end_time:
                    end_dt = datetime.combine(end_date_obj, datetime.strptime(end_time, '%H:%M').time())
                else:
                    end_dt = datetime.combine(end_date_obj, dt_time.max)
                
                start_dt = timezone.make_aware(start_dt)
                end_dt = timezone.make_aware(end_dt)
                
                sales = sales.filter(timestamp__gte=start_dt, timestamp__lte=end_dt)
            
        except Exception as e:
            import traceback
            traceback.print_exc()

    # Calculate expenses for the filtered period
    expenses = Expense.objects.all()
    if date_filter == 'today':
        expenses = expenses.filter(expense_date=today_baku)
    elif date_filter == 'week':
        start_of_week_baku = now_baku - timedelta(days=now_baku.weekday())
        expenses = expenses.filter(expense_date__gte=start_of_week_baku.date())
    elif date_filter == 'month':
        expenses = expenses.filter(expense_date__year=now_baku.year, expense_date__month=now_baku.month)
    elif date_filter == 'custom' and start_date and end_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            expenses = expenses.filter(expense_date__gte=start_date_obj, expense_date__lte=end_date_obj)
        except:
            pass

    if shop_id:
        expenses = expenses.filter(shop_id=shop_id)

    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Calculate total revenue, items sold, number of sales, average sale
    total_revenue = sales.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
    items_sold = sales.aggregate(total=Sum('quantity'))['total'] or 0
    num_sales = sales.count()
    avg_sale = sales.aggregate(avg=Avg('total_price'))['avg'] or Decimal('0.00')

    # Calculate total profit
    profit_expr = ExpressionWrapper(
        (F('good__price') - F('good__buy_price')) * F('quantity'),
        output_field=FloatField()
    )
    total_profit = sales.aggregate(total=Sum(profit_expr))['total'] or 0

    # Calculate net profit (profit - expenses)
    net_profit = Decimal(str(total_profit)) - total_expenses

    # Today / week / month revenue with Azerbaijan time adjustment
    today_sales = Sale.objects.filter(timestamp__date=today_baku)
    today_revenue = today_sales.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')

    start_of_week_baku = now_baku - timedelta(days=now_baku.weekday())
    start_of_week_utc = start_of_week_baku - azerbaijan_offset
    week_sales = Sale.objects.filter(timestamp__gte=start_of_week_utc)
    week_revenue = week_sales.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')

    month_sales = Sale.objects.filter(
        timestamp__year=now_baku.year,
        timestamp__month=now_baku.month
    )
    month_revenue = month_sales.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')

    context = {
        'shops': shops,
        'categories': categories,
        'sales': sales[:50],
        'expenses': expenses,
        'total_revenue': total_revenue,
        'total_profit': total_profit,
        'net_profit': net_profit,
        'total_expenses': total_expenses,
        'items_sold': items_sold,
        'num_sales': num_sales,
        'avg_sale': avg_sale,
        'today_revenue': today_revenue,
        'week_revenue': week_revenue,
        'month_revenue': month_revenue,
        'filters': {
            'shop': shop_id,
            'category': category_id,
            'barcode': barcode,
            'date_filter': date_filter,
            'start_date': start_date,
            'end_date': end_date,
            'start_time': start_time,
            'end_time': end_time,
            'worker_shift': worker_shift,
        },
        'current_baku_time': now_baku.strftime('%Y-%m-%d %H:%M:%S')
    }

    return render(request, 'shop/finance.html', context)
