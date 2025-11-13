# Smoking Shop Management System

A Django-based web application for managing multiple smoking shops with barcode-based sales and comprehensive finance tracking.

## Features

### Admin Panel (Superadmin)
- Full CRUD operations for shops, categories, goods, and sales
- Search and filter goods by barcode, shop, and category
- Manage inventory across multiple shops
- Edit prices and stock counts inline

### Worker Dashboard
- Barcode scanner integration for quick sales
- Live shopping cart with quantity management
- Built-in calculator for change calculation
- Real-time stock validation
- Clean, tablet-friendly interface

### Finance Dashboard
- Sales statistics and analytics
- Filter by shop, category, barcode, and date range
- Summary cards for today, week, and month
- Detailed sales history table
- Revenue and performance metrics

## Tech Stack

- **Framework**: Django 4.2
- **Database**: SQLite
- **Frontend**: Tailwind CSS (CDN)
- **Templates**: Django Templates

## Installation

1. Install dependencies:
```bash
apt-get install python3-django python3-pip
```

2. Run migrations:
```bash
python3 manage.py migrate
```

3. Create superuser and sample data:
```bash
python3 setup_data.py
```

## Usage

### Start the development server:
```bash
python3 manage.py runserver 0.0.0.0:8000
```

### Access the application:
- **Admin Panel**: http://localhost:8000/admin/
- **Worker Dashboard**: http://localhost:8000/worker/
- **Finance Dashboard**: http://localhost:8000/finance/

### Default Admin Credentials:
- Username: `admin`
- Password: `admin123`

## Database Models

### Shop
- name

### Category
- name

### Good
- name
- price
- stock_count
- barcode
- category (ForeignKey)
- shop (ForeignKey)

### Sale
- good (ForeignKey)
- quantity
- total_price
- timestamp (auto_now_add)
- shop (ForeignKey)

## Worker Dashboard Usage

1. Select a shop from the dropdown
2. Focus on the barcode input field
3. Scan items using a barcode scanner (or type manually)
4. Items automatically appear in the cart
5. Adjust quantities or remove items as needed
6. Use the calculator to calculate change
7. Click "Complete Sale" to finalize

The system automatically:
- Updates stock counts
- Creates sale records
- Validates stock availability

## Finance Dashboard Usage

### Filters Available:
- **Shop**: Filter by specific shop
- **Category**: Filter by product category
- **Barcode**: Search specific products
- **Date Range**: Today, This Week, This Month, or Custom

### Metrics Displayed:
- Total revenue for selected period
- Number of items sold
- Number of sales transactions
- Average sale value
- Daily, weekly, and monthly summaries

## Future Enhancements

- Worker login system with shop-specific access
- Export reports to CSV/Excel
- Low stock alerts and notifications
- Real-time updates using Django Channels
- Chart visualizations with Chart.js
- Multi-language support
- Print receipt functionality
- Customer management system

## Sample Data

The setup script creates:
- 3 shops (Main Store, Downtown Branch, Airport Shop)
- 5 categories (Cigarettes, Cigars, Vapes, Accessories, Tobacco)
- 10 sample products with barcodes

## Notes

- Barcode scanners work as keyboard input devices
- The system treats scanner input as normal text entry
- Stock counts are automatically decremented on sale
- All timestamps are recorded for audit purposes
- The admin panel provides full control over all data
