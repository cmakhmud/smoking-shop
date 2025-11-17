from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from datetime import datetime
from django.utils import timezone

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

    def __str__(self):
        # Safe __str__ method that won't crash
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
