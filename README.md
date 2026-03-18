# Django Subscription Billing Backend

A comprehensive subscription billing system built with Django, Celery, and Redis that supports user subscriptions, automatic invoice generation, payment processing, and billing lifecycle management.

## Features

### Core Functionality
- **User Management**: Built on Django's authentication system
- **Subscription Plans**: Basic, Pro, and Enterprise tiers
- **Subscription Management**: Subscribe, cancel, and track subscription status
- **Automatic Invoice Generation**: Celery-powered monthly billing cycles
- **Payment Processing**: Mock Stripe integration with real payment intent creation
- **Billing Lifecycle**: Complete tracking from subscription to payment

### Advanced Features
- **Overdue Invoice Detection**: Automatic marking of past-due invoices
- **Payment Reminders**: Automated email notifications (console output for demo)
- **Stripe Integration**: Real Stripe API integration for payment processing
- **RESTful APIs**: Complete API endpoints for all operations
- **Admin Interface**: Django admin for easy management
- **Periodic Tasks**: Celery Beat for scheduled operations

## 🛠 Technology Stack

- **Backend**: Django 4.2.7
- **Task Queue**: Celery 5.3.4
- **Message Broker**: Redis 5.0.1
- **API**: Django REST Framework 3.14.0
- **Payment Processing**: Stripe 7.8.0
- **Database**: SQLite (easily configurable for PostgreSQL/MySQL)

##  Installation

### Prerequisites
- Python 3.8+
- Redis server
- Git

### Step 1: Clone the Repository
```bash
git clone https://github.com/devs001/demo_pro.git
cd demo_pro
```

### Step 2: Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Environment Configuration
Create a `.env` file in the project root:
```env
SECRET_KEY=your-secret-key-here
DEBUG=True
STRIPE_PUBLISHABLE_KEY=pk_test_your_stripe_publishable_key
STRIPE_SECRET_KEY=sk_test_your_stripe_secret_key
```

### Step 5: Database Setup
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

### Step 6: Create Sample Data
create samle data from this 
'''
plans_data = [
            {'name': 'basic', 'price': 9.99, 'features': 'Basic features, 5GB storage'},
            {'name': 'pro', 'price': 19.99, 'features': 'Pro features, 50GB storage, Priority support'},
            {'name': 'enterprise', 'price': 49.99, 'features': 'Enterprise features, Unlimited storage, 24/7 support'},
        ]
'''

## 🏃‍♂️ Running the Application

### Start Redis Server
```bash
redis-server
```

### Start Django Development Server
```bash
python manage.py runserver
```

### Start Celery Worker
```bash
celery -A billing_project worker --loglevel=info
```

### Start Celery Beat (Periodic Tasks)
```bash
celery -A billing_project beat --loglevel=info
```

## 📡 API Endpoints

### Authentication
All endpoints except plan listing require authentication. Use Django's session authentication or implement token authentication as needed.

### Plans
```http
GET /api/plans/
```
**Description**: List all available subscription plans
**Authentication**: Not required

### Subscriptions
```http
POST /api/subscribe/
Content-Type: application/json

{
    "plan": 1
}
```
**Description**: Subscribe user to a plan

```http
GET /api/subscriptions/
```
**Description**: List user's subscriptions

```http
POST /api/subscriptions/{subscription_id}/cancel/
```
**Description**: Cancel a subscription

### Invoices
```http
GET /api/invoices/
```
**Description**: List user's invoices

```http
POST /api/invoices/{invoice_id}/pay/
```
**Description**: Process payment for an invoice

## 📊 Database Models

### Plan
- `name`: Plan type (basic, pro, enterprise)
- `price`: Monthly price
- `billing_cycle_days`: Billing cycle length (default: 30)
- `features`: Plan features description
- `is_active`: Plan availability status

### Subscription
- `user`: Foreign key to User
- `plan`: Foreign key to Plan
- `status`: active, cancelled, expired, pending
- `start_date`: Subscription start date
- `end_date`: Subscription end date
- `next_billing_date`: Next billing cycle date
- `stripe_subscription_id`: Stripe subscription ID

### Invoice
- `user`: Foreign key to User
- `subscription`: Foreign key to Subscription
- `plan`: Foreign key to Plan
- `amount`: Invoice amount
- `status`: pending, paid, overdue, cancelled
- `issue_date`: Invoice creation date
- `due_date`: Payment due date
- `invoice_number`: Unique invoice identifier

##  Celery Tasks

### Periodic Tasks (Celery Beat)
- **Daily Invoice Generation**: Runs at midnight to create invoices for due subscriptions
- **Overdue Invoice Marking**: Runs at 6 AM to mark overdue invoices

### Manual Tasks
- **create_invoice_for_subscription**: Create invoice for specific subscription
- **send_payment_reminder**: Send payment reminder for overdue invoices

##  Stripe Integration

The system includes real Stripe integration for payment processing:

1. **Payment Intents**: Creates Stripe PaymentIntent for invoice payments
2. **Webhook Support**: Ready for Stripe webhook integration
3. **Metadata Tracking**: Links Stripe transactions to internal invoices

### Stripe Configuration
Add your Stripe keys to the `.env` file:
```env
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
```

## 🧪 Testing the System

### 1. Create Test User and Login
```bash
python manage.py shell
```
```python
from django.contrib.auth.models import User
user = User.objects.create_user('testuser', 'test@example.com', 'password123')
```

### 2. Test API Endpoints
Use tools like Postman, curl, or Django's browsable API:

```bash
# Login and get session
curl -X POST http://localhost:8000/admin/login/ \
  -d "username=testuser&password=password123"

# Subscribe to a plan
curl -X POST http://localhost:8000/api/subscribe/ \
  -H "Content-Type: application/json" \
  -d '{"plan": 1}' \
  --cookie-jar cookies.txt

# View invoices
curl -X GET http://localhost:8000/api/invoices/ \
  --cookie cookies.txt
```

### 3. Monitor Celery Tasks
Check the Celery worker logs to see task execution:
- Invoice generation
- Overdue marking
- Payment reminders


### 1. Email Reminders
- Automated payment reminders for overdue invoices
- Console output for demonstration (easily configurable for real email)
- Includes invoice details and user information

### 2. Stripe Integration
- Real Stripe API integration
- PaymentIntent creation for invoice payments
- Webhook-ready architecture
- Secure payment processing

### 3. Advanced Admin Interface
- Comprehensive Django admin interface
- Filterable and searchable models
- Bulk operations support
- Read-only fields for system-generated data

### 4. Robust Error Handling
- Comprehensive error handling in API endpoints
- Detailed error messages
- Logging for debugging and monitoring
- Graceful degradation for failed tasks


### 1. Database Design
- Used UUIDs for subscriptions and invoices for security
- Proper foreign key relationships with cascading deletes
- Indexed fields for performance
- Audit trail with created/updated timestamps

### 2. Task Queue Architecture
- Separated immediate tasks (invoice creation) from periodic tasks
- Retry mechanisms for failed tasks
- Comprehensive logging for monitoring
- Scalable task distribution

### 3. API Design
- RESTful endpoints following Django REST Framework conventions
- Proper HTTP status codes
- Consistent error response format
- Authentication and permission handling

## 🔧 Configuration Options

### Database
Switch to PostgreSQL for production:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'billing_db',
        'USER': 'your_user',
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```
