from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from .models import Plan

class Command(BaseCommand):
    help = 'Create sample data for testing'

    def handle(self, *args, **options):
        # Create plans
        plans_data = [
            {'name': 'basic', 'price': 9.99, 'features': 'Basic features, 5GB storage'},
            {'name': 'pro', 'price': 19.99, 'features': 'Pro features, 50GB storage, Priority support'},
            {'name': 'enterprise', 'price': 49.99, 'features': 'Enterprise features, Unlimited storage, 24/7 support'},
        ]

        for plan_data in plans_data:
            plan, created = Plan.objects.get_or_create(
                name=plan_data['name'],
                defaults=plan_data
            )
            if created:
                self.stdout.write(f"Created plan: {plan.name}")

        # Create test user
        user, created = User.objects.get_or_create(
            username='testuser',
            defaults={
                'email': 'test@example.com',
                'first_name': 'Test',
                'last_name': 'User'
            }
        )
        if created:
            user.set_password('testpass123')
            user.save()
            self.stdout.write("Created test user: testuser")

        self.stdout.write(self.style.SUCCESS('Sample data created successfully!'))