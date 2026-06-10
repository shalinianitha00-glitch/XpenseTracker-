from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Budget, Category, SavingsGoal, Transaction, UserPreference
import re


class ExpenseForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["category"].queryset = Category.objects.filter(user=user)

    class Meta:
        model = Transaction
        fields = ["title", "transaction_type", "amount", "category", "date", "payment_method", "notes", "status"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


class IncomeForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["category"].queryset = Category.objects.filter(user=user)

    class Meta:
        model = Transaction
        fields = ["title", "amount", "category", "date", "payment_method", "notes", "status"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.transaction_type = "income"
        if commit:
            instance.save()
        return instance


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "emoji", "color"]
        widgets = {
            "color": forms.TextInput(attrs={"type": "color"}),
        }


class BudgetForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["category"].queryset = Category.objects.filter(user=user).exclude(name="Income")

    class Meta:
        model = Budget
        fields = ["category", "amount", "month"]
        widgets = {
            "month": forms.DateInput(attrs={"type": "date"}),
        }


class SavingsGoalForm(forms.ModelForm):
    class Meta:
        model = SavingsGoal
        fields = ["name", "goal_type", "emoji", "saved_amount", "target_amount", "deadline"]
        widgets = {
            "deadline": forms.DateInput(attrs={"type": "date"}),
        }


class PreferenceForm(forms.ModelForm):
    theme = forms.ChoiceField(choices=[("dark", "Dark Navy"), ("light", "Light"), ("ocean", "Ocean Cyan"), ("sunset", "Sunset Pink")])
    currency = forms.ChoiceField(choices=[("INR", "INR (₹)")])
    date_format = forms.ChoiceField(choices=[("DD/MM/YYYY", "DD/MM/YYYY")])

    class Meta:
        model = UserPreference
        fields = [
            "name",
            "email",
            "theme",
            "currency",
            "date_format",
            "show_currency_symbol",
            "expense_notifications",
            "weekly_summary_emails",
            "enable_sounds",
            "daily_expense_reminder_enabled",
            "daily_expense_reminder_time",
        ]
        widgets = {
            "daily_expense_reminder_time": forms.TimeInput(attrs={"type": "time"}),
        }

class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=80, required=False)

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "email",
            "password1",
            "password2",
        ]

    def clean_username(self):
        username = self.cleaned_data["username"]

        if len(username) < 4:
            raise forms.ValidationError(
                "Username must be at least 4 characters."
            )

        return username

    def clean_password1(self):
        password = self.cleaned_data.get("password1")

        if len(password) < 8:
            raise forms.ValidationError(
                "Password must be at least 8 characters long."
            )

        if not re.search(r"[A-Z]", password):
            raise forms.ValidationError(
                "Password must contain at least one uppercase letter."
            )

        if not re.search(r"[a-z]", password):
            raise forms.ValidationError(
                "Password must contain at least one lowercase letter."
            )

        if not re.search(r"\d", password):
            raise forms.ValidationError(
                "Password must contain at least one number."
            )

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            raise forms.ValidationError(
                "Password must contain at least one special character."
            )

        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data.get("first_name", "")

        if commit:
            user.save()

        return user