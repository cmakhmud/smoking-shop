from django.shortcuts import render, get_object_or_404 ,redirect  
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count, Avg, Q ,ExpressionWrapper ,F ,FloatField
from django.contrib import messages
from decimal import Decimal
import json
import uuid
from django.core.cache import cache
from django.utils import timezone
from datetime import datetime, time as dt_time ,timedelta
import logging
import pytz
from django.contrib.auth.decorators import login_required
# Add these missing imports
from django.db import connection ,transaction
from django.contrib.auth.models import User
from django.conf import settings
from .models import Shop, Category, Good, Sale, Expense ,Debt, DebtItem , StockReceipt

logger = logging.getLogger(__name__)

from .models import Shop, Category, Good, Sale

def search_goods(request):
    query = request.GET.get('q', '').strip()
    shop_id = request.GET.get('shop_id')
    
    if not query or not shop_id:
        return JsonResponse({'results': []})
    
    try:
        # KEEP stock_count__gt=0 for sales search
        goods = Good.objects.filter(
            Q(name__icontains=query) | Q(barcode__icontains=query),
            shop_id=shop_id,
            stock_count__gt=0  # ← KEEP THIS for sales
        )[:10]
        
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


def scan_barcode(request):
    data = json.loads(request.body)
    barcode = data.get('barcode', '').strip()
    shop_id = data.get('shop_id')

    if not barcode or not shop_id:
        return JsonResponse({'error': 'Barcode and shop are required'}, status=400)

    try:
        # KEEP stock_count__gt=0 filter for sales - don't show goods with 0 stock
        good = Good.objects.select_related('category').only(
            'id', 'name', 'price', 'barcode', 'stock_count', 'category__name'
        ).get(
            barcode=barcode,
            shop_id=shop_id,
            stock_count__gt=0  # ← KEEP THIS for sales
        )

        return JsonResponse({
            'id': good.id,
            'name': good.name,
            'price': float(good.price),
            'category': good.category.name,
            'stock_count': good.stock_count,
            'barcode': good.barcode
        })
        
    except Good.DoesNotExist:
        return JsonResponse({'error': 'Good not found with this barcode'}, status=404)


@require_http_methods(["POST"])
def process_sale(request):
    # First, check if request body exists
    if not request.body:
        return JsonResponse({'error': 'Empty request body'}, status=400)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    
    # Add request ID check
    request_id = data.get('request_id', str(uuid.uuid4()))
    cache_key = f'sale_request_{request_id}'
    
    # Check if this request was already processed
    if cache.get(cache_key):
        return JsonResponse({
            'success': True, 
            'message': 'Sale already processed (duplicate request ignored)'
        })
    
    items = data.get('items', [])
    shop_id = data.get('shop_id')

    if not items or not shop_id:
        return JsonResponse({'error': 'Items and shop are required'}, status=400)

    try:
        shop = get_object_or_404(Shop, id=shop_id)
        current_time = timezone.now()
        
        # Use a transaction to ensure atomicity
        with transaction.atomic():
            sales_to_create = []
            goods_to_update = []
            
            # Validate all items first WITH SELECT FOR UPDATE to lock rows
            for item in items:
                # Use select_for_update() to lock the goods row
                good = Good.objects.select_for_update().get(id=item['id'], shop=shop)
                quantity = int(item['quantity'])
                
                if good.stock_count < quantity:
                    return JsonResponse({
                        'error': f'Insufficient stock for {good.name}. Available: {good.stock_count}'
                    }, status=400)
                
                # Prepare sale record
                sales_to_create.append(Sale(
                    good=good,
                    quantity=quantity,
                    total_price=good.price * quantity,
                    shop=shop,
                    timestamp=current_time
                ))
                
                # Update stock count
                good.stock_count -= quantity
                goods_to_update.append(good)
            
            # Bulk create all sales
            Sale.objects.bulk_create(sales_to_create)
            
            # Bulk update all goods
            for good in goods_to_update:
                good.save()
            
            # Mark request as processed (store for 30 seconds)
            cache.set(cache_key, True, timeout=30)
        
        return JsonResponse({
            'success': True, 
            'message': 'Sale completed successfully',
            'request_id': request_id  # Return the request ID
        })
        
    except Exception as e:
        logger.error(f"Error processing sale: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
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

    # Get regular sales
    sales = Sale.objects.select_related('good', 'shop', 'good__category').all()

    if shop_id:
        sales = sales.filter(shop_id=shop_id)
    if category_id:
        sales = sales.filter(good__category_id=category_id)
    if barcode:
        sales = sales.filter(good__barcode__icontains=barcode)

    # Get ALL debts (including paid ones) for revenue calculation
    # But only pending debts for current operations
    all_debts = Debt.objects.select_related('shop').all()
    pending_debts = all_debts.filter(status='pending')
    
    if shop_id:
        all_debts = all_debts.filter(shop_id=shop_id)
        pending_debts = pending_debts.filter(shop_id=shop_id)

    # Use Django's timezone system instead of pytz
    now = timezone.now()
    azerbaijan_offset = timedelta(hours=4)
    now_baku = now + azerbaijan_offset
    today_baku = now_baku.date()

    # Date filter for both sales and debts
    if date_filter == 'today':
        sales = sales.filter(timestamp__date=today_baku)
        all_debts = all_debts.filter(created_at__date=today_baku)
        pending_debts = pending_debts.filter(created_at__date=today_baku)
    elif date_filter == 'week':
        start_of_week = now_baku - timedelta(days=now_baku.weekday())
        start_of_week_utc = start_of_week - azerbaijan_offset
        sales = sales.filter(timestamp__gte=start_of_week_utc)
        all_debts = all_debts.filter(created_at__gte=start_of_week_utc)
        pending_debts = pending_debts.filter(created_at__gte=start_of_week_utc)
    elif date_filter == 'month':
        sales = sales.filter(
            timestamp__year=now_baku.year,
            timestamp__month=now_baku.month
        )
        all_debts = all_debts.filter(
            created_at__year=now_baku.year,
            created_at__month=now_baku.month
        )
        pending_debts = pending_debts.filter(
            created_at__year=now_baku.year,
            created_at__month=now_baku.month
        )
    elif date_filter == 'custom' and start_date and end_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            if not start_time and not end_time:
                sales = sales.filter(timestamp__date__gte=start_date_obj, timestamp__date__lte=end_date_obj)
                all_debts = all_debts.filter(created_at__date__gte=start_date_obj, created_at__date__lte=end_date_obj)
                pending_debts = pending_debts.filter(created_at__date__gte=start_date_obj, created_at__date__lte=end_date_obj)
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
                all_debts = all_debts.filter(created_at__gte=start_dt, created_at__lte=end_dt)
                pending_debts = pending_debts.filter(created_at__gte=start_dt, created_at__lte=end_dt)
            
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

    # Calculate revenue from both sales and ALL debts (including paid ones)
    sales_revenue = sales.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
    debts_revenue = all_debts.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    total_revenue = sales_revenue + debts_revenue

    # Calculate items sold (from both sales and ALL debts)
    sales_items_sold = sales.aggregate(total=Sum('quantity'))['total'] or 0
    debts_items_sold = DebtItem.objects.filter(debt__in=all_debts).aggregate(total=Sum('quantity'))['total'] or 0
    items_sold = sales_items_sold + debts_items_sold

    # Calculate number of transactions (sales + ALL debts)
    num_sales = sales.count() + all_debts.count()

    # Calculate average sale
    avg_sale = total_revenue / num_sales if num_sales > 0 else Decimal('0.00')

    # Calculate total profit (from both sales and ALL debts)
    sales_profit_expr = ExpressionWrapper(
        (F('good__price') - F('good__buy_price')) * F('quantity'),
        output_field=FloatField()
    )
    sales_profit = sales.aggregate(total=Sum(sales_profit_expr))['total'] or 0

    # For ALL debts, profit is (selling price - buy price) * quantity
    debt_items = DebtItem.objects.filter(debt__in=all_debts).select_related('good')
    debts_profit = Decimal('0.00')
    for debt_item in debt_items:
        item_profit = (debt_item.unit_price - debt_item.good.buy_price) * debt_item.quantity
        debts_profit += item_profit

    total_profit = Decimal(str(sales_profit)) + debts_profit

    # Calculate net profit (profit - expenses)
    net_profit = total_profit - total_expenses

    # Today / week / month revenue with Azerbaijan time adjustment (including ALL debts)
    today_sales = Sale.objects.filter(timestamp__date=today_baku)
    today_all_debts = Debt.objects.filter(created_at__date=today_baku)
    today_revenue = (today_sales.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')) + \
                   (today_all_debts.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00'))

    start_of_week_baku = now_baku - timedelta(days=now_baku.weekday())
    start_of_week_utc = start_of_week_baku - azerbaijan_offset
    week_sales = Sale.objects.filter(timestamp__gte=start_of_week_utc)
    week_all_debts = Debt.objects.filter(created_at__gte=start_of_week_utc)
    week_revenue = (week_sales.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')) + \
                  (week_all_debts.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00'))

    month_sales = Sale.objects.filter(
        timestamp__year=now_baku.year,
        timestamp__month=now_baku.month
    )
    month_all_debts = Debt.objects.filter(
        created_at__year=now_baku.year,
        created_at__month=now_baku.month
    )
    month_revenue = (month_sales.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')) + \
                   (month_all_debts.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00'))

    # Combine sales and pending debts for display (only show pending debts in the list)
    combined_sales = []
    
    # Add regular sales
    for sale in sales[:25]:  # Show first 25 sales
        combined_sales.append({
            'type': 'sale',
            'timestamp': sale.timestamp,
            'good_name': sale.good.name,
            'category': sale.good.category.name,
            'shop_name': sale.shop.name,
            'quantity': sale.quantity,
            'total_price': sale.total_price,
            'is_debt': False
        })
    
    # Add pending debts (limited to keep total around 50 items)
    debt_count = min(25, pending_debts.count())
    for debt in pending_debts[:debt_count]:
        combined_sales.append({
            'type': 'debt',
            'timestamp': debt.created_at,
            'good_name': f"BORC: {debt.customer_name}",
            'category': 'Borc Satışı',
            'shop_name': debt.shop.name,
            'quantity': 1,  # Representing one debt transaction
            'total_price': debt.total_amount,
            'is_debt': True,
            'customer_name': debt.customer_name
        })
    
    # Sort by timestamp and take first 50
    combined_sales.sort(key=lambda x: x['timestamp'], reverse=True)
    combined_sales = combined_sales[:50]

    context = {
        'shops': shops,
        'categories': categories,
        'sales': combined_sales,
        'expenses': expenses,
        'total_revenue': total_revenue,
        'sales_revenue': sales_revenue,
        'debts_revenue': debts_revenue,
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
        'current_baku_time': now_baku.strftime('%Y-%m-%d %H:%M:%S'),
        'sales_count': sales.count(),
        'debts_count': all_debts.count(),  # Count of ALL debts for revenue breakdown
        'pending_debts_count': pending_debts.count()  # Count of pending debts for operations
    }

    return render(request, 'shop/finance.html', context)

@login_required
def create_debt_page(request):
    shops = Shop.objects.all()
    return render(request, 'shop/create_debt.html', {'shops': shops})

@login_required
def debt_list(request):
    debts = Debt.objects.select_related('shop').all()
    
    # Filters
    shop_id = request.GET.get('shop')
    status = request.GET.get('status')
    
    if shop_id:
        debts = debts.filter(shop_id=shop_id)
    if status:
        debts = debts.filter(status=status)

    # Statistics
    total_debts = debts.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    total_paid = debts.aggregate(total=Sum('paid_amount'))['total'] or Decimal('0.00')
    total_remaining = debts.aggregate(total=Sum('remaining_amount'))['total'] or Decimal('0.00')
    
    today = timezone.now().date()
    overdue_debts = debts.filter(due_date__lt=today, status='pending')
    total_overdue = overdue_debts.aggregate(total=Sum('remaining_amount'))['total'] or Decimal('0.00')

    context = {
        'debts': debts,
        'shops': Shop.objects.all(),
        'today': today,
        'total_debts': total_debts,
        'total_paid': total_paid,
        'total_remaining': total_remaining,
        'total_overdue': total_overdue,
        'overdue_count': overdue_debts.count(),
        'filters': {
            'shop': shop_id,
            'status': status,
        }
    }
    
    return render(request, 'shop/debt_list.html', context)

@login_required
@require_http_methods(["POST"])
def create_debt(request):
    data = json.loads(request.body)
    
    customer_name = data.get('customer_name')
    customer_phone = data.get('customer_phone', '')
    shop_id = data.get('shop_id')
    items = data.get('items', [])
    due_date = data.get('due_date')
    description = data.get('description', '')

    if not customer_name or not shop_id or not items or not due_date:
        return JsonResponse({'error': 'Bütün məlumatları doldurun'}, status=400)

    try:
        shop = Shop.objects.get(id=shop_id)
        due_date_obj = datetime.strptime(due_date, '%Y-%m-%d').date()
        
        # Calculate total amount and check stock
        total_amount = Decimal('0.00')
        debt_items_data = []
        
        # First, check all items have sufficient stock
        for item in items:
            good = Good.objects.get(id=item['id'], shop=shop)
            if good.stock_count < item['quantity']:
                return JsonResponse({
                    'error': f'{good.name} üçün kifayət qədər stok yoxdur. Stok: {good.stock_count}, Tələb olunan: {item["quantity"]}'
                }, status=400)
            
            item_total = good.price * item['quantity']
            total_amount += item_total
            
            debt_items_data.append({
                'good': good,
                'quantity': item['quantity'],
                'unit_price': good.price,
                'total_price': item_total
            })

        # Create debt
        debt = Debt.objects.create(
            customer_name=customer_name,
            customer_phone=customer_phone,
            shop=shop,
            total_amount=total_amount,
            remaining_amount=total_amount,
            due_date=due_date_obj,
            description=description,
            created_by=request.user
        )

        # Create debt items and reduce stock
        for item_data in debt_items_data:
            DebtItem.objects.create(
                debt=debt,
                good=item_data['good'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                total_price=item_data['total_price']
            )
            
            # Reduce stock - IMPORTANT: Stock decreases when debt is created
            good = item_data['good']
            good.stock_count -= item_data['quantity']
            good.save()

        return JsonResponse({
            'success': True,
            'debt_id': debt.id,
            'message': f'Borc uğurla yaradıldı. Ümumi məbləğ: {total_amount} AZN. Stok yeniləndi.'
        })

    except Good.DoesNotExist:
        return JsonResponse({'error': 'Məhsul tapılmadı'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_http_methods(["POST"])
def pay_debt(request):
    try:
        data = json.loads(request.body)
        debt_id = data.get('debt_id')
        amount_str = data.get('amount', '0')
        
        # Debug logging
        print(f"DEBUG: Received payment - debt_id: {debt_id}, amount: {amount_str}")

        if not debt_id or not amount_str:
            return JsonResponse({'error': 'Borc ID və məbləğ tələb olunur'}, status=400)

        # Convert amount to Decimal with proper handling
        try:
            amount = Decimal(amount_str)
        except (Decimal.InvalidOperation, ValueError):
            return JsonResponse({'error': 'Düzgün məbləğ formatı daxil edin (məs: 5.40, 0.50)'}, status=400)

        if amount <= 0:
            return JsonResponse({'error': 'Məbləğ müsbət olmalıdır'}, status=400)

        debt = Debt.objects.get(id=debt_id)
        
        if debt.status != 'pending':
            return JsonResponse({'error': 'Bu borc artıq ödənilib və ya ləğv edilib'}, status=400)

        # Round to 2 decimal places to avoid floating point issues
        amount = amount.quantize(Decimal('0.01'))
        
        if amount > debt.remaining_amount:
            return JsonResponse({
                'error': f'Ödəniş məbləği qalan məbləğdən çox ola bilməz. Qalan: {debt.remaining_amount:.2f} AZN'
            }, status=400)

        debt.paid_amount += amount
        debt.save()

        return JsonResponse({
            'success': True,
            'message': f'{amount:.2f} AZN ödəniş qəbul edildi. Qalan məbləğ: {debt.remaining_amount:.2f} AZN',
            'remaining_amount': float(debt.remaining_amount)
        })

    except Debt.DoesNotExist:
        return JsonResponse({'error': 'Borc tapılmadı'}, status=404)
    except Exception as e:
        print(f"ERROR in pay_debt: {str(e)}")  # Debug logging
        return JsonResponse({'error': f'Xəta baş verdi: {str(e)}'}, status=500)

@login_required
@require_http_methods(["POST"])
def cancel_debt(request):
    data = json.loads(request.body)
    debt_id = data.get('debt_id')

    if not debt_id:
        return JsonResponse({'error': 'Borc ID tələb olunur'}, status=400)

    try:
        debt = Debt.objects.get(id=debt_id)
        
        if debt.status != 'pending':
            return JsonResponse({'error': 'Yalnız gözləyən borclar ləğv edilə bilər'}, status=400)

        # Restore stock for all items in this debt
        debt_items = DebtItem.objects.filter(debt=debt)
        for debt_item in debt_items:
            good = debt_item.good
            good.stock_count += debt_item.quantity
            good.save()

        # Update debt status
        debt.status = 'cancelled'
        debt.save()

        return JsonResponse({
            'success': True,
            'message': 'Borc ləğv edildi və stok geri qaytarıldı'
        })

    except Debt.DoesNotExist:
        return JsonResponse({'error': 'Borc tapılmadı'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def worker_open_pack(request):
    """Worker view to open cigarette packs - accessible by workers and admin"""
    # Get worker's shop or admin can access all
    worker_shop = None
    if hasattr(request.user, 'worker'):
        worker_shop = request.user.worker.shop
    elif not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "Bu səhifəyə giriş hüququnuz yoxdur")
        return redirect('shop:worker')
    
    if request.method == 'POST':
        barcode = request.POST.get('barcode', '').strip()
        
        if not barcode:
            messages.error(request, "Zəhmət olmasa barkod daxil edin")
        else:
            try:
                # For admin users, don't filter by shop
                if request.user.is_staff or request.user.is_superuser:
                    pack_product = Good.objects.get(
                        barcode=barcode,
                        product_type='cigarette_pack'
                    )
                else:
                    # For workers, filter by their shop
                    pack_product = Good.objects.get(
                        barcode=barcode,
                        product_type='cigarette_pack',
                        shop=worker_shop
                    )
                
                if pack_product.stock_count > 0:
                    # Decrease pack quantity
                    pack_product.stock_count -= 1
                    pack_product.save()
                    
                    # Find related single cigarettes
                    if pack_product.related_singles.exists():
                        single_product = pack_product.related_singles.first()
                        single_product.stock_count += 20
                        single_product.save()
                        
                        messages.success(
                            request,
                            f"✅ Uğurla 1 paçka {pack_product.name} açıldı. "
                            f"20 ədəd stək əlavə edildi. "
                            f"Paçka stok: {pack_product.stock_count}, "
                            f"Ədəd stok: {single_product.stock_count}"
                        )
                    else:
                        messages.error(
                            request,
                            f"❌ {pack_product.name} üçün əlaqəli stək məhsulu tapılmadı"
                        )
                else:
                    messages.error(
                        request,
                        f"❌ {pack_product.name} üçün kifayət qədər stok yoxdur"
                    )
                    
            except Good.DoesNotExist:
                messages.error(request, "❌ Bu barkodla məhsul tapılmadı")
            except Good.MultipleObjectsReturned:
                # If multiple products found (admin case), show selection options
                if request.user.is_staff or request.user.is_superuser:
                    packs = Good.objects.filter(
                        barcode=barcode,
                        product_type='cigarette_pack'
                    )
                    context = {
                        'multiple_packs': packs,
                        'barcode': barcode,
                        'worker_shop': worker_shop,
                        'available_packs': Good.objects.filter(
                            product_type='cigarette_pack',
                            stock_count__gt=0
                        ).select_related('category', 'shop')
                    }
                    return render(request, 'shop/select_pack.html', context)
                else:
                    messages.error(request, "❌ Bu barkodla birdən çox məhsul tapıldı")
            except Exception as e:
                messages.error(request, f"❌ Xəta baş verdi: {str(e)}")
    
    # Get available packs for display
    if request.user.is_staff or request.user.is_superuser:
        # Admin can see all packs from all shops
        available_packs = Good.objects.filter(
            product_type='cigarette_pack',
            stock_count__gt=0
        ).select_related('category', 'shop')
    else:
        # Workers only see packs from their shop
        available_packs = Good.objects.filter(
            product_type='cigarette_pack',
            shop=worker_shop,
            stock_count__gt=0
        ).select_related('category')
    
    context = {
        'available_packs': available_packs,
        'worker_shop': worker_shop,
        'is_admin': request.user.is_staff or request.user.is_superuser
    }
    return render(request, 'shop/worker_open_pack.html', context)

@login_required
@require_http_methods(["POST"])
def api_open_pack(request):
    """API endpoint for opening packs via barcode scan - accessible by workers and admin"""
    data = json.loads(request.body)
    barcode = data.get('barcode', '').strip()
    shop_id = data.get('shop_id')  # For admin to specify shop
    
    # Check if user has permission
    if not (hasattr(request.user, 'worker') or request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'error': 'Bu əməliyyatı yerinə yetirmək hüququnuz yoxdur'}, status=403)
    
    try:
        # For admin users, they can specify shop_id or work with any
        if request.user.is_staff or request.user.is_superuser:
            if shop_id:
                pack_product = Good.objects.get(
                    barcode=barcode,
                    product_type='cigarette_pack',
                    shop_id=shop_id
                )
            else:
                pack_product = Good.objects.get(
                    barcode=barcode,
                    product_type='cigarette_pack'
                )
        else:
            # For workers, use their assigned shop
            worker_shop = request.user.worker.shop
            pack_product = Good.objects.get(
                barcode=barcode,
                product_type='cigarette_pack',
                shop=worker_shop
            )
        
        if pack_product.stock_count > 0:
            # Decrease pack quantity
            pack_product.stock_count -= 1
            pack_product.save()
            
            # Find related single cigarettes
            if pack_product.related_singles.exists():
                single_product = pack_product.related_singles.first()
                single_product.stock_count += 20
                single_product.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'1 paçka {pack_product.name} açıldı. 20 ədəd stək əlavə edildi.',
                    'pack_stock': pack_product.stock_count,
                    'single_stock': single_product.stock_count,
                    'pack_name': pack_product.name,
                    'single_name': single_product.name,
                    'shop_name': pack_product.shop.name
                })
            else:
                return JsonResponse({
                    'error': f'{pack_product.name} üçün əlaqəli stək məhsulu tapılmadı'
                }, status=400)
        else:
            return JsonResponse({
                'error': f'{pack_product.name} üçün kifayət qədər stok yoxdur'
            }, status=400)
            
    except Good.DoesNotExist:
        return JsonResponse({'error': 'Bu barkodla məhsul tapılmadı'}, status=404)
    except Good.MultipleObjectsReturned:
        # Return available options for admin
        if request.user.is_staff or request.user.is_superuser:
            packs = Good.objects.filter(
                barcode=barcode,
                product_type='cigarette_pack'
            ).select_related('shop')
            pack_options = [{
                'id': pack.id,
                'name': pack.name,
                'shop_name': pack.shop.name,
                'stock_count': pack.stock_count
            } for pack in packs]
            return JsonResponse({
                'multiple_options': True,
                'message': 'Birdən çox məhsul tapıldı',
                'packs': pack_options
            }, status=300)
        else:
            return JsonResponse({'error': 'Bu barkodla birdən çox məhsul tapıldı'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Xəta baş verdi: {str(e)}'}, status=500)
    

@require_http_methods(["POST"])
def scan_barcode_for_stock(request):
    """For stock receipt/management - finds goods even with 0 stock"""
    data = json.loads(request.body)
    barcode = data.get('barcode', '').strip()
    shop_id = data.get('shop_id')

    if not barcode or not shop_id:
        return JsonResponse({'error': 'Barcode and shop are required'}, status=400)

    try:
        # NO stock filter - find goods even with 0 stock
        good = Good.objects.select_related('category').only(
            'id', 'name', 'price', 'barcode', 'stock_count', 'category__name', 'buy_price'
        ).get(
            barcode=barcode,
            shop_id=shop_id
            # No stock_count__gt=0 filter here
        )

        return JsonResponse({
            'id': good.id,
            'name': good.name,
            'price': float(good.price),
            'buy_price': float(good.buy_price),
            'category': good.category.name,
            'stock_count': good.stock_count,  # This can be 0
            'barcode': good.barcode
        })
        
    except Good.DoesNotExist:
        return JsonResponse({'error': 'Good not found with this barcode'}, status=404)

# NEW FUNCTION for stock management search
def search_goods_for_stock(request):
    """For stock receipt/management - finds goods even with 0 stock"""
    query = request.GET.get('q', '').strip()
    shop_id = request.GET.get('shop_id')
    
    if not query or not shop_id:
        return JsonResponse({'results': []})
    
    try:
        # NO stock filter for stock management
        goods = Good.objects.filter(
            Q(name__icontains=query) | Q(barcode__icontains=query),
            shop_id=shop_id
            # No stock_count__gt=0 filter here
        )[:10]
        
        results = []
        for good in goods:
            results.append({
                'id': good.id,
                'name': good.name,
                'price': float(good.price),
                'buy_price': float(good.buy_price),
                'barcode': good.barcode,
                'category': good.category.name if good.category else '',
                'stock_count': good.stock_count  # Can be 0
            })
        
        return JsonResponse({'results': results})
        
    except Exception as e:
        return JsonResponse({'error': 'Axtarış xətası'}, status=500)

@login_required
def stock_receipt(request):
    """Stock receipt page for workers and admin - multiple items with costs"""
    worker_shop = None
    if hasattr(request.user, 'worker'):
        worker_shop = request.user.worker.shop
    elif not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "Bu səhifəyə giriş hüququnuz yoxdur")
        return redirect('shop:worker')
    
    shops = Shop.objects.all()
    categories = Category.objects.all()
    
    if request.method == 'POST':
        items_data = request.POST.get('items_data', '')
        notes = request.POST.get('notes', '')
        supplier = request.POST.get('supplier', '')
        receipt_type = request.POST.get('receipt_type', 'purchase')
        shop_id = request.POST.get('shop_id')
        
        print(f"=== STOCK RECEIPT POST DATA ===")
        print(f"items_data length: {len(items_data)}")
        print(f"notes: {notes}")
        print(f"supplier: {supplier}")
        print(f"receipt_type: {receipt_type}")
        print(f"shop_id: {shop_id}")
        
        if not items_data or items_data == '[]' or items_data == 'null':
            messages.error(request, "Əlavə edilmiş məhsul yoxdur")
            return redirect('shop:stock_receipt')
        
        try:
            # Determine which shop to use
            if request.user.is_staff or request.user.is_superuser:
                if shop_id:
                    target_shop = Shop.objects.get(id=shop_id)
                    print(f"DEBUG: Admin selected shop_id={shop_id}, shop_name={target_shop.name}")
                else:
                    messages.error(request, "Admin üçün mağaza seçmək məcburidir")
                    return redirect('shop:stock_receipt')
            else:
                target_shop = worker_shop
                print(f"DEBUG: Worker shop = {worker_shop.id if worker_shop else 'None'}")
            
            # Parse items data
            try:
                items = json.loads(items_data)
                print(f"DEBUG: Parsed {len(items)} items")
                print(f"DEBUG: Items data: {items}")
            except json.JSONDecodeError as je:
                print(f"DEBUG: JSON decode error: {je}")
                print(f"DEBUG: Problematic JSON: {items_data[:200]}")
                messages.error(request, f"JSON məlumatları düzgün deyil: {str(je)}")
                return redirect('shop:stock_receipt')
            
            success_count = 0
            total_cost = Decimal('0.00')
            error_messages = []
            
            for index, item in enumerate(items):
                try:
                    print(f"DEBUG: Processing item {index + 1}/{len(items)}: {item}")
                    
                    # Validate item data
                    if 'id' not in item:
                        error_messages.append(f"Item {index + 1}: ID yoxdur")
                        continue
                    
                    item_id = item['id']
                    if not item_id:
                        error_messages.append(f"Item {index + 1}: ID boşdur")
                        continue
                    
                    good = Good.objects.get(id=item_id, shop=target_shop)
                    print(f"DEBUG: Found good: {good.name} (ID: {good.id})")
                    
                    # Ensure proper data types
                    quantity = int(item.get('quantity', 1))
                    unit_cost_str = str(item.get('unit_cost', '0')).replace(',', '.')
                    unit_cost = Decimal(unit_cost_str)
                    
                    print(f"DEBUG: quantity={quantity}, unit_cost={unit_cost}")
                    
                    # Create stock receipt
                    StockReceipt.objects.create(
                        good=good,
                        quantity=quantity,
                        receipt_type=receipt_type,
                        unit_cost=unit_cost,
                        supplier=supplier,
                        notes=notes,
                        created_by=request.user,
                        shop=target_shop
                    )
                    success_count += 1
                    total_cost += unit_cost * quantity
                    print(f"DEBUG: Created receipt for {good.name}")
                    
                except Good.DoesNotExist:
                    error_msg = f"{item.get('name', f'Item {index + 1}')} - Məhsul tapılmadı"
                    error_messages.append(error_msg)
                    print(f"DEBUG: {error_msg}")
                except ValueError as ve:
                    error_msg = f"{item.get('name', f'Item {index + 1}')} - Dəyər xətası: {str(ve)}"
                    error_messages.append(error_msg)
                    print(f"DEBUG: Value error: {ve}")
                except Exception as e:
                    error_msg = f"{item.get('name', f'Item {index + 1}')} - Xəta: {str(e)}"
                    error_messages.append(error_msg)
                    print(f"DEBUG: Item error: {e}")
                    import traceback
                    traceback.print_exc()
            
            if success_count > 0:
                success_msg = f"✅ {success_count} məhsulun stoku uğurla əlavə edildi! Ümumi dəyər: {total_cost:.2f} AZN"
                messages.success(request, success_msg)
                print(f"DEBUG: Success - {success_msg}")
            
            if error_messages:
                warning_msg = f"⚠️ {len(error_messages)} məhsulda xəta: " + ", ".join(error_messages[:3])
                if len(error_messages) > 3:
                    warning_msg += f" və {len(error_messages) - 3} digəri"
                messages.warning(request, warning_msg)
                print(f"DEBUG: Warnings - {warning_msg}")
            
        except Exception as e:
            error_msg = f"❌ Xəta baş verdi: {str(e)}"
            messages.error(request, error_msg)
            print(f"DEBUG: General exception: {e}")
            import traceback
            traceback.print_exc()
        
        return redirect('shop:stock_receipt')
    
    # Get recent receipts for display
    if request.user.is_staff or request.user.is_superuser:
        recent_receipts = StockReceipt.objects.select_related('good').order_by('-created_at')[:10]
    else:
        recent_receipts = StockReceipt.objects.filter(shop=worker_shop).select_related('good').order_by('-created_at')[:10]
    
    context = {
        'worker_shop': worker_shop,
        'shops': shops,
        'categories': categories,
        'recent_receipts': recent_receipts,
        'is_admin': request.user.is_staff or request.user.is_superuser
    }
    return render(request, 'shop/stock_receipt.html', context)

@login_required
@require_http_methods(["POST"])
def api_stock_receipt(request):
    """API endpoint for stock receipt via barcode scan"""
    data = json.loads(request.body)
    barcode = data.get('barcode', '').strip()
    quantity = data.get('quantity', 1)
    receipt_type = data.get('receipt_type', 'purchase')
    unit_cost = data.get('unit_cost', 0)
    supplier = data.get('supplier', '')
    shop_id = data.get('shop_id')
    
    # Check permissions
    if not (hasattr(request.user, 'worker') or request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'error': 'Bu əməliyyatı yerinə yetirmək hüququnuz yoxdur'}, status=403)
    
    try:
        # Determine shop
        if request.user.is_staff or request.user.is_superuser:
            if not shop_id:
                return JsonResponse({'error': 'Admin üçün mağaza seçmək məcburidir'}, status=400)
            target_shop = Shop.objects.get(id=shop_id)
        else:
            target_shop = request.user.worker.shop
        
        # Find product - NO stock filter for stock management
        good = Good.objects.get(barcode=barcode, shop=target_shop)
        
        # Create stock receipt
        stock_receipt = StockReceipt.objects.create(
            good=good,
            quantity=quantity,
            receipt_type=receipt_type,
            unit_cost=unit_cost,
            supplier=supplier,
            created_by=request.user,
            shop=target_shop
        )
        
        return JsonResponse({
            'success': True,
            'message': f'{quantity} ədəd {good.name} stoka əlavə edildi',
            'new_stock': good.stock_count,
            'good_name': good.name,
            'receipt_id': stock_receipt.id
        })
        
    except Good.DoesNotExist:
        return JsonResponse({'error': 'Bu barkodla məhsul tapılmadı'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Xəta baş verdi: {str(e)}'}, status=500)
    
@login_required
@require_http_methods(["POST"])
def create_good_api(request):
    """API endpoint for creating new goods"""
    try:
        data = json.loads(request.body)
        print("DEBUG: Creating new product with data:", data)
        
        # Tələb olunan sahələri yoxla
        required_fields = ['name', 'price', 'buy_price', 'shop_id']
        for field in required_fields:
            if field not in data:
                return JsonResponse({'error': f'{field} tələb olunur'}, status=400)
        
        # Mağazanı yoxla
        try:
            shop = Shop.objects.get(id=data['shop_id'])
        except Shop.DoesNotExist:
            return JsonResponse({'error': 'Mağaza tapılmadı'}, status=404)
        
        # Barcode kontrolü
        barcode = data.get('barcode', '').strip()
        if barcode:
            # Barcode'un bu mağazada mövcud olub olmadığını yoxla
            if Good.objects.filter(barcode=barcode, shop=shop).exists():
                return JsonResponse({'error': 'Bu barkod artıq bu mağazada mövcuddur'}, status=400)
        
        # Yeni məhsul yarat
        good = Good(
            name=data['name'],
            price=Decimal(str(data['price'])),
            buy_price=Decimal(str(data['buy_price'])),
            barcode=barcode,
            shop=shop,
            product_type=data.get('product_type', 'normal'),
            stock_count=0  # Yeni məhsulun stoku 0 olur
        )
        
        # Kateqoriya əlavə et
        if 'category_id' in data and data['category_id']:
            try:
                category = Category.objects.get(id=data['category_id'])
                good.category = category
            except Category.DoesNotExist:
                return JsonResponse({'error': 'Kateqoriya tapılmadı'}, status=404)
        else:
            # Default kateqoriya təyin et (ilk kateqoriyanı)
            first_category = Category.objects.first()
            if first_category:
                good.category = first_category
        
        good.save()
        
        return JsonResponse({
            'success': True,
            'good': {
                'id': good.id,
                'name': good.name,
                'barcode': good.barcode,
                'price': float(good.price),
                'buy_price': float(good.buy_price),
                'stock_count': good.stock_count,
                'category': good.category.name if good.category else '',
                'category_id': good.category.id if good.category else None
            },
            'message': 'Məhsul uğurla yaradıldı'
        })
        
    except Exception as e:
        print(f"ERROR creating good: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f'Xəta baş verdi: {str(e)}'}, status=500)

@login_required
def api_categories(request):
    """API endpoint to get all categories"""
    categories = Category.objects.all().values('id', 'name')
    return JsonResponse({'categories': list(categories)})