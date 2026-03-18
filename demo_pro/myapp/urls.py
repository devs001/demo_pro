from django.urls import path
from . import views

urlpatterns = [
    path('plans/', views.PlanListView.as_view(), name='plan-list'),
    path('subscribe/', views.subscribe_to_plan, name='subscribe'),
    path('subscriptions/', views.UserSubscriptionsView.as_view(), name='user-subscriptions'),
    path('subscriptions/<uuid:subscription_id>/cancel/', views.cancel_subscription, name='cancel-subscription'),
    path('invoices/', views.UserInvoicesView.as_view(), name='user-invoices'),
    path('invoices/<uuid:invoice_id>/pay/', views.pay_invoice, name='pay-invoice'),
    path('webhook/', views.WebhookView.as_view(), name='webhook'),

]