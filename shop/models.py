from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from datetime import datetime
from django.utils import timezone
from decimal import Decimal

class Shop(models.Model):
    name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Category(models.Model):
    name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Categories'


class Good(models.Model):
    PRODUCT_TYPES = [
        ('normal', 'Normal Product'),
        ('cigarette_pack', 'Cigarette Pack (20)'),
        ('cigarette_single', 'Single Cigarette'),
    ]
    
    name = models.CharField(max_length=200)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    buy_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )
    stock_count = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    barcode = models.CharField(max_length=100, db_index=True)
    category = models.ForeignKey(
        'Category', 
        on_delete=models.CASCADE, 
        related_name='goods'
    )
    shop = models.ForeignKey(
        'Shop', 
        on_delete=models.CASCADE, 
        related_name='goods'
    )

    # Add these new fields
    product_type = models.CharField(
        max_length=20, 
        choices=PRODUCT_TYPES, 
        default='normal'
    )
    related_pack = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        limit_choices_to={'product_type': 'cigarette_pack'},
        related_name='related_singles'
    )
    def __str__(self):
        shop_name = self.shop.name if self.shop else "No Shop"
        return f"{self.name} - {shop_name}"

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['barcode', 'shop']),
        ]

class Sale(models.Model):
    good = models.ForeignKey(Good, on_delete=models.CASCADE, related_name='sales')
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    total_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    timestamp = models.DateTimeField(default=datetime.now)  # ← Use datetime.now
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='sales')

    def __str__(self):
        return f"{self.good.name} x{self.quantity} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        ordering = ['-timestamp']


class Worker(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.shop.name}"

    class Meta:
        verbose_name = "İşçi"
        verbose_name_plural = "İşçilər"

class Expense(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    expense_date = models.DateField(default=timezone.now)

    def __str__(self):
        return f"{self.shop.name} - {self.amount} - {self.expense_date}"

    class Meta:
        ordering = ['-expense_date', '-created_at']

class Debt(models.Model):
    DEBT_STATUS = [
        ('pending', 'Gözləyir'),
        ('paid', 'Ödənilib'),
        ('cancelled', 'Ləğv edilib'),
    ]

    customer_name = models.CharField(max_length=200, verbose_name="Müştəri adı")
    customer_phone = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, verbose_name="Mağaza")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Ümumi məbləğ")
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Ödənilən məbləğ")
    remaining_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Qalan məbləğ")
    status = models.CharField(max_length=20, choices=DEBT_STATUS, default='pending', verbose_name="Status")
    due_date = models.DateField(verbose_name="Son tarix")
    description = models.TextField(blank=True, verbose_name="Qeyd")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Yaradan")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.remaining_amount = self.total_amount - self.paid_amount
        if self.remaining_amount <= 0 and self.status == 'pending':
            self.status = 'paid'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.customer_name} - {self.total_amount} AZN"

    class Meta:
        verbose_name = "Borc"
        verbose_name_plural = "Borclar"
        ordering = ['-created_at']


class DebtItem(models.Model):
    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, related_name='items')
    good = models.ForeignKey(Good, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.good.name} x {self.quantity}"

class StockReceipt(models.Model):
    RECEIPT_TYPES = [
        ('purchase', 'Satın Alma'),
        ('transfer', 'Transfer'),
        ('adjustment', 'Stok Düzeltme'),
    ]
    
    good = models.ForeignKey(Good, on_delete=models.CASCADE, related_name='stock_receipts')
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    receipt_type = models.CharField(max_length=20, choices=RECEIPT_TYPES, default='purchase')
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], default=0)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], default=0)
    supplier = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def clean(self):
        """Validation before saving"""
        super().clean()
        
        # Ensure the good belongs to the same shop
        if self.good.shop != self.shop:
            raise ValidationError("Good does not belong to the selected shop.")
    
    def save(self, *args, **kwargs):
        # Convert to Decimal to ensure proper calculation
        quantity_decimal = Decimal(str(self.quantity))
        unit_cost_decimal = Decimal(str(self.unit_cost))
        
        # Calculate total cost before saving
        self.total_cost = quantity_decimal * unit_cost_decimal
        
        # Check if this is a new record or an update
        if self.pk is None:  # New record
            # Update good stock count
            self.good.stock_count += self.quantity
            self.good.save()
        else:  # Updating existing record
            # Get the old receipt to calculate the difference
            old_receipt = StockReceipt.objects.get(pk=self.pk)
            quantity_diff = self.quantity - old_receipt.quantity
            
            # Update good stock count by the difference
            self.good.stock_count += quantity_diff
            self.good.save()
        
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        # When deleting a receipt, subtract the quantity from stock
        self.good.stock_count -= self.quantity
        self.good.save()
        super().delete(*args, **kwargs)
    
    def __str__(self):
        return f"{self.good.name} - {self.quantity} adet - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Stok Qəbulu"
        verbose_name_plural = "Stok Qəbulları"
