from datetime import date, time

from django.conf import settings
from django.db import models
from django.utils import timezone


def current_month_start():
    today = timezone.localdate()
    return date(today.year, today.month, 1)


class Category(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categories", null=True, blank=True)
    name = models.CharField(max_length=80)
    emoji = models.CharField(max_length=8, default="□")
    color = models.CharField(max_length=16, default="#8b3dff")

    class Meta:
        ordering = ["name"]
        unique_together = ["user", "name"]

    def __str__(self):
        return self.name


class Transaction(models.Model):
    TYPE_CHOICES = [
        ("income", "Income"),
        ("expense", "Expense"),
    ]

    STATUS_CHOICES = [
        ("Completed", "Completed"),
        ("Paid", "Paid"),
        ("Received", "Received"),
        ("Pending", "Pending"),
    ]

    title = models.CharField(max_length=120)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions", null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="expense")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="transactions")
    date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    payment_method = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Completed")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def signed_amount(self):
        return self.amount if self.transaction_type == "income" else -self.amount


class Budget(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="budgets", null=True, blank=True)
    category = models.OneToOneField(Category, on_delete=models.CASCADE, related_name="budget")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    month = models.DateField(default=current_month_start)

    class Meta:
        ordering = ["category__name"]

    @property
    def spent(self):
        return sum(
            tx.amount for tx in self.category.transactions.filter(
                transaction_type="expense",
                date__year=self.month.year,
                date__month=self.month.month,
            )
        )

    @property
    def progress(self):
        if not self.amount:
            return 0
        return min(round((self.spent / self.amount) * 100), 100)

    @property
    def status(self):
        progress = self.progress
        if progress >= 95:
            return "Exceeded"
        if progress >= 80:
            return "Warning"
        return "On Track"


class SavingsGoal(models.Model):
    GOAL_TYPE_CHOICES = [
        ("savings", "Savings Goal"),
        ("emergency", "Emergency Fund"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="savings_goals", null=True, blank=True)
    name = models.CharField(max_length=100)
    goal_type = models.CharField(max_length=20, choices=GOAL_TYPE_CHOICES, default="savings")
    emoji = models.CharField(max_length=8, default="🏦")
    saved_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    deadline = models.DateField()

    class Meta:
        ordering = ["deadline"]

    @property
    def progress(self):
        if not self.target_amount:
            return 0
        return min(round((self.saved_amount / self.target_amount) * 100), 100)

    @property
    def days_left(self):
        return max((self.deadline - timezone.localdate()).days, 0)


class UserPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preference", null=True, blank=True)
    name = models.CharField(max_length=80, default="")
    email = models.EmailField(default="")
    theme = models.CharField(max_length=12, default="dark")
    currency = models.CharField(max_length=8, default="INR")
    date_format = models.CharField(max_length=16, default="DD/MM/YYYY")
    show_currency_symbol = models.BooleanField(default=True)
    expense_notifications = models.BooleanField(default=True)
    weekly_summary_emails = models.BooleanField(default=False)
    enable_sounds = models.BooleanField(default=False)
    daily_expense_reminder_enabled = models.BooleanField(default=True)
    daily_expense_reminder_time = models.TimeField(default=time(20, 0))
