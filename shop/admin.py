from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Shop, Category, Good, Sale, Worker , Expense , Debt , DebtItem ,StockReceipt


class WorkerInline(admin.StackedInline):
    model = Worker
    can_delete = False
    verbose_name_plural = 'İşçi Məlumatları'
    fields = ['shop', 'phone']


class CustomUserAdmin(UserAdmin):
    inlines = (WorkerInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_shop', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active')  # REMOVED 'worker__shop'
    
    def get_shop(self, obj):
        try:
            if hasattr(obj, 'worker') and obj.worker.shop:
                return obj.worker.shop.name
        except:
            pass
        return "Admin"
    get_shop.short_description = 'Mağaza'


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ['user', 'shop', 'phone', 'created_at']
    list_filter = ['shop', 'created_at']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'phone']
    autocomplete_fields = ['user', 'shop']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Əsas Məlumatlar', {
            'fields': ('user', 'shop', 'phone')
        }),
        ('Qeydiyyat Məlumatları', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ['name', 'get_worker_count']
    search_fields = ['name']
    
    def get_worker_count(self, obj):
        return obj.worker_set.count()
    get_worker_count.short_description = 'İşçi Sayı'


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


@admin.register(Good)
class GoodAdmin(admin.ModelAdmin):
    list_display = ['name', 'barcode', 'price', 'buy_price', 'stock_count', 'category', 'shop']
    list_filter = ['shop', 'category']
    search_fields = ['name', 'barcode']
    list_editable = ['price', 'buy_price', 'stock_count']


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['good', 'quantity', 'total_price', 'shop', 'timestamp']
    list_filter = ['shop', 'timestamp', 'good__category']
    search_fields = ['good__name', 'good__barcode']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('shop', 'amount', 'description', 'created_by', 'expense_date', 'created_at')
    list_filter = ('shop', 'expense_date', 'created_by')
    search_fields = ('description', 'shop__name', 'created_by__username')
    date_hierarchy = 'expense_date'
    ordering = ('-expense_date', '-created_at')
    
    # This will show the fields in the admin form
    fieldsets = (
        ('Əsas Məlumatlar', {
            'fields': ('shop', 'amount', 'expense_date', 'description')
        }),
        ('Əlavə Məlumatlar', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    # Make created_by and created_at read-only when editing
    readonly_fields = ('created_by', 'created_at')
    
    # Auto-set the created_by field when adding new expense
    def save_model(self, request, obj, form, change):
        if not obj.pk:  # If this is a new object (not editing existing)
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(Debt)
class DebtAdmin(admin.ModelAdmin):
    list_display = ('customer_name', 'customer_phone', 'shop', 'total_amount', 'paid_amount', 'remaining_amount', 'status', 'due_date', 'created_by')
    list_filter = ('shop', 'status', 'due_date', 'created_at')
    search_fields = ('customer_name', 'customer_phone', 'description')
    readonly_fields = ('remaining_amount', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'

@admin.register(DebtItem)
class DebtItemAdmin(admin.ModelAdmin):
    list_display = ('debt', 'good', 'quantity', 'unit_price', 'total_price')
    list_filter = ('debt__shop',)

@admin.register(StockReceipt)
class StockReceiptAdmin(admin.ModelAdmin):
    list_display = ['good', 'quantity', 'receipt_type', 'unit_cost', 'total_cost', 'supplier', 'shop', 'created_by', 'created_at']
    list_filter = ['receipt_type', 'shop', 'created_at']
    search_fields = ['good__name', 'supplier']
    readonly_fields = ['total_cost', 'created_at']
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)