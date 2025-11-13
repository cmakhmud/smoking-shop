import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smokingshop.settings')
django.setup()

from django.contrib.auth.models import User
from shop.models import Shop, Category, Good

print("Creating superuser...")
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print("Superuser created: username='admin', password='admin123'")
else:
    print("Superuser already exists")

print("\nCreating sample data...")

shops_data = ['Main Store', 'Downtown Branch', 'Airport Shop']
for shop_name in shops_data:
    shop, created = Shop.objects.get_or_create(name=shop_name)
    if created:
        print(f"Created shop: {shop_name}")

categories_data = ['Cigarettes', 'Cigars', 'Vapes', 'Accessories', 'Tobacco']
for category_name in categories_data:
    category, created = Category.objects.get_or_create(name=category_name)
    if created:
        print(f"Created category: {category_name}")

sample_goods = [
    {'name': 'Marlboro Red', 'barcode': '1234567890', 'price': 12.50, 'stock': 100, 'category': 'Cigarettes'},
    {'name': 'Camel Blue', 'barcode': '1234567891', 'price': 11.00, 'stock': 80, 'category': 'Cigarettes'},
    {'name': 'Lucky Strike', 'barcode': '1234567892', 'price': 10.50, 'stock': 60, 'category': 'Cigarettes'},
    {'name': 'Cuban Cigar Premium', 'barcode': '2234567890', 'price': 45.00, 'stock': 30, 'category': 'Cigars'},
    {'name': 'Dominican Cigar', 'barcode': '2234567891', 'price': 35.00, 'stock': 40, 'category': 'Cigars'},
    {'name': 'JUUL Starter Kit', 'barcode': '3234567890', 'price': 55.00, 'stock': 50, 'category': 'Vapes'},
    {'name': 'Vuse Alto', 'barcode': '3234567891', 'price': 45.00, 'stock': 45, 'category': 'Vapes'},
    {'name': 'Zippo Lighter', 'barcode': '4234567890', 'price': 25.00, 'stock': 70, 'category': 'Accessories'},
    {'name': 'Rolling Papers', 'barcode': '4234567891', 'price': 3.50, 'stock': 200, 'category': 'Accessories'},
    {'name': 'Pipe Tobacco Premium', 'barcode': '5234567890', 'price': 18.00, 'stock': 55, 'category': 'Tobacco'},
]

main_store = Shop.objects.get(name='Main Store')

for good_data in sample_goods:
    category = Category.objects.get(name=good_data['category'])
    good, created = Good.objects.get_or_create(
        barcode=good_data['barcode'],
        shop=main_store,
        defaults={
            'name': good_data['name'],
            'price': good_data['price'],
            'stock_count': good_data['stock'],
            'category': category,
        }
    )
    if created:
        print(f"Created good: {good_data['name']}")

print("\n✅ Setup complete!")
print("\nAdmin credentials:")
print("  Username: admin")
print("  Password: admin123")
print("\nYou can now:")
print("  1. Access admin panel at: http://localhost:8000/admin/")
print("  2. Access worker dashboard at: http://localhost:8000/worker/")
print("  3. Access finance dashboard at: http://localhost:8000/finance/")
