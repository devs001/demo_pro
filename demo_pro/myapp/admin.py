from django.contrib import admin
from .models import Plan, Subscription, Invoice

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'billing_cycle_days', 'is_active', 'created_at']
    list_filter = ['name', 'is_active']
    search_fields = ['name']

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'status', 'start_date', 'end_date', 'next_billing_date']
    list_filter = ['status', 'plan', 'created_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['id', 'created_at', 'updated_at']

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'user', 'plan', 'amount', 'status', 'issue_date', 'due_date']
    list_filter = ['status', 'plan', 'issue_date']
    search_fields = ['invoice_number', 'user__username', 'user__email']
    readonly_fields = ['id', 'invoice_number', 'issue_date']