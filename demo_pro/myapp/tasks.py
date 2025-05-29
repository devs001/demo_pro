from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Subscription, Invoice
import logging

logger = logging.getLogger(__name__)

@shared_task
def create_invoice_for_subscription(subscription_id):
    """Create an invoice for a specific subscription"""
    try:
        subscription = Subscription.objects.get(id=subscription_id)

        # Create invoice
        invoice = Invoice.objects.create(
            user=subscription.user,
            subscription=subscription,
            plan=subscription.plan,
            amount=subscription.plan.price,
            due_date=timezone.now() + timedelta(days=7)
        )

        logger.info(f"Created invoice {invoice.invoice_number} for subscription {subscription_id}")
        return f"Invoice {invoice.invoice_number} created successfully"

    except Subscription.DoesNotExist:
        logger.error(f"Subscription {subscription_id} not found")
        return f"Subscription {subscription_id} not found"

@shared_task
def generate_monthly_invoices():
    """Generate invoices for all subscriptions due for billing"""
    today = timezone.now().date()

    # Find subscriptions that need billing today
    subscriptions_due = Subscription.objects.filter(
        status='active',
        next_billing_date__date=today
    )

    invoices_created = 0

    for subscription in subscriptions_due:
        # Check if invoice already exists for this billing cycle
        existing_invoice = Invoice.objects.filter(
            subscription=subscription,
            issue_date__date=today
        ).exists()

        if not existing_invoice:
            create_invoice_for_subscription.delay(str(subscription.id))

            # Update next billing date
            subscription.next_billing_date = subscription.next_billing_date + timedelta(
                days=subscription.plan.billing_cycle_days
            )
            subscription.save()

            invoices_created += 1

    logger.info(f"Generated {invoices_created} invoices")
    return f"Generated {invoices_created} invoices"

@shared_task
def mark_overdue_invoices():
    """Mark invoices as overdue if they're past due date"""
    overdue_invoices = Invoice.objects.filter(
        status='pending',
        due_date__lt=timezone.now()
    )

    count = 0
    for invoice in overdue_invoices:
        invoice.status = 'overdue'
        invoice.save()
        count += 1

        send_payment_reminder.delay(str(invoice.id))

    logger.info(f"Marked {count} invoices as overdue")
    return f"Marked {count} invoices as overdue"

@shared_task
def send_payment_reminder(invoice_id):
    """Send payment reminder for overdue invoice (mock implementation)"""
    try:
        invoice = Invoice.objects.get(id=invoice_id)

        # Mock email sending (in
        print(f"PAYMENT REMINDER EMAIL")
        print(f"To: {invoice.user.email}")
        print(f"Subject: Payment Overdue - Invoice {invoice.invoice_number}")
        print(f"Dear {invoice.user.first_name or invoice.user.username},")
        print(f"Your invoice {invoice.invoice_number} for ${invoice.amount} is overdue.")
        print(f"Please make payment as soon as possible to avoid service interruption.")
        print(f"Due date: {invoice.due_date.strftime('%Y-%m-%d')}")
        print(f"Amount: ${invoice.amount}")
        print("=" * 50)

        logger.info(f"Payment reminder sent for invoice {invoice_id}")
        return f"Payment reminder sent for invoice {invoice_id}"

    except Invoice.DoesNotExist:
        logger.error(f"Invoice {invoice_id} not found")
        return f"Invoice {invoice_id} not found"