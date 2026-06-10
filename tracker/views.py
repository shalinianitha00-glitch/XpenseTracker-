import csv
import json
import calendar as calendar_lib
from datetime import date
from decimal import Decimal
from urllib import request

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import BudgetForm, CategoryForm, ExpenseForm, PreferenceForm, SavingsGoalForm, SignUpForm
from .models import Budget, Category, SavingsGoal, Transaction, UserPreference


DEFAULT_CATEGORIES = [
    ("Food & Dining", "🍔", "#ff4d75"),
    ("Transport", "🚗", "#2491ff"),
    ("Shopping", "🛍️", "#ffc21a"),
    ("Entertainment", "🎮", "#8d4dff"),
    ("Bills & Utilities", "💡", "#31d06f"),
    ("Income", "💼", "#2ddd6f"),
    ("Others", "⚙️", "#8091a8"),
]


def money(value, preference=None):
    number = Decimal(value or 0)

    symbol = "₹"

    if preference:
        if preference.currency == "USD":
            symbol = "$"
        elif preference.currency == "EUR":
            symbol = "€"

    sign = "-" if number < 0 else ""

    return f"{sign}{symbol}{abs(number):,.2f}"


def selected_month(request):
    raw = request.GET.get("month", "")
    today = timezone.localdate()
    try:
        year, month = [int(part) for part in raw.split("-", 1)]
        return date(year, month, 1)
    except (TypeError, ValueError):
        return date(today.year, today.month, 1)


def shift_month(month_start, offset):
    month = month_start.month + offset
    year = month_start.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, 1)


def ensure_user_defaults(user):
    if not user.is_authenticated:
        return None
    for name, emoji, color in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(user=user, name=name, defaults={"emoji": emoji, "color": color})
    preference, _ = UserPreference.objects.get_or_create(
        user=user,
        defaults={
            "name": user.first_name or user.username,
            "email": user.email or f"{user.username}@example.com",
        },
    )
    if not preference.theme:
        preference.theme = "dark"
        preference.save(update_fields=["theme"])
    return preference


def category_rows(user, total_expenses):
    rows = []
    for category in Category.objects.filter(user=user):
        spent = category.transactions.filter(transaction_type="expense").aggregate(total=Sum("amount"))["total"] or Decimal("0")
        percent = round((spent / total_expenses) * 100, 1) if total_expenses else 0
        rows.append(
            {
                "id": category.id,
                "name": category.name,
                "emoji": category.emoji,
                "color": category.color,
                "spent": spent,
                "percent": percent,
            }
        )
    return rows


def transaction_rows(queryset):
    return [
        {
            "id": item.id,
            "date": item.date.strftime("%b %d, %Y"),
            "raw_date": item.date,
            "description": item.title,
            "category": item.category.name,
            "icon": item.category.emoji,
            "amount": item.signed_amount,
            "status": item.status,
            "type": item.transaction_type,
            "notes": item.notes,
        }
        for item in queryset
    ]


def goal_rows():
    return []


def user_goal_rows(user):
    average_monthly_expenses = average_user_monthly_expenses(user)
    recommended_emergency_fund = average_monthly_expenses * 3
    rows = []
    for goal in SavingsGoal.objects.filter(user=user):
        emergency_progress = round((goal.saved_amount / recommended_emergency_fund) * 100) if recommended_emergency_fund else 0
        is_emergency_goal = goal.goal_type == "emergency"
        display_progress = min(emergency_progress, 100) if is_emergency_goal else goal.progress
        display_target = recommended_emergency_fund if is_emergency_goal else goal.target_amount
        preparedness_status, emergency_alert = emergency_status(emergency_progress)
        rows.append({
            "id": goal.id,
            "name": goal.name,
            "goal_type": goal.goal_type,
            "emoji": goal.emoji,
            "saved": goal.saved_amount,
            "target": goal.target_amount,
            "progress": goal.progress,
            "display_progress": display_progress,
            "display_target": display_target,
            "days": goal.days_left,
            "deadline": goal.deadline,
            "recommended_emergency_fund": recommended_emergency_fund,
            "emergency_progress": min(emergency_progress, 100),
            "preparedness_status": preparedness_status,
            "emergency_alert": emergency_alert,
        }
        )
    return rows


def average_user_monthly_expenses(user):
    expenses = Transaction.objects.filter(user=user, transaction_type="expense")
    monthly_totals = {}
    for item in expenses:
        key = (item.date.year, item.date.month)
        monthly_totals[key] = monthly_totals.get(key, Decimal("0")) + item.amount
    if not monthly_totals:
        return Decimal("0")
    return sum(monthly_totals.values(), Decimal("0")) / Decimal(len(monthly_totals))


def emergency_status(progress):
    if progress > 100:
        return "Excellent", "✅ Emergency fund is in good condition. You are financially prepared for most unexpected situations."
    if progress >= 71:
        return "Well Prepared", "✅ Emergency fund is in good condition. You are financially prepared for most unexpected situations."
    if progress >= 31:
        return "Building Fund", ""
    return "Needs Attention", "⚠ Emergency fund is below recommended level. Unexpected expenses may impact financial stability."


def emergency_fund_summary(user):
    recommended = average_user_monthly_expenses(user) * 3
    current = SavingsGoal.objects.filter(user=user, goal_type="emergency").aggregate(total=Sum("saved_amount"))["total"] or Decimal("0")
    progress = round((current / recommended) * 100) if recommended else 0
    status, alert = emergency_status(progress)
    return {
        "recommended": recommended,
        "current": current,
        "progress": progress,
        "status": status,
        "alert": alert,
    }


def budget_rows(user):
    rows = []
    for budget in Budget.objects.select_related("category").filter(user=user):
        remaining = budget.amount - budget.spent
        progress = budget.progress
        exceeded_amount = abs(remaining) if remaining < 0 else 0
        category_name = budget.category.name.lower()
        if "food" in category_name:
            financial_suggestion = "Consider reducing food delivery and dining expenses for the remainder of the month."
        elif "shopping" in category_name:
            financial_suggestion = "Delay non-essential purchases until next month."
        elif "entertainment" in category_name:
            financial_suggestion = "Reduce discretionary spending and focus on priority expenses."
        elif "transport" in category_name:
            financial_suggestion = "Consider optimizing travel costs where possible."
        elif "bill" in category_name or "utilit" in category_name:
            financial_suggestion = "Review utility usage to identify savings opportunities."
        else:
            financial_suggestion = "Review spending patterns and reduce non-essential expenses."

        if progress > 100:
            budget_alert_type = "exceeded"
            budget_alert_message = "🚨 Budget Exceeded"
        elif progress == 100:
            budget_alert_type = "limit"
            budget_alert_message = "⚠ Budget Limit Reached"
        elif progress >= 80:
            budget_alert_type = "warning"
            budget_alert_message = "⚠ Budget Warning"
        else:
            budget_alert_type = ""
            budget_alert_message = ""

        rows.append(
            {
                "id": budget.id,
                "category": budget.category.name,
                "budget": budget.amount,
                "spent": budget.spent,
                "remaining_budget": remaining,
                "exceeded_amount": exceeded_amount,
                "progress": progress,
                "status": budget.status,
                "budget_alert_type": budget_alert_type,
                "budget_alert_message": budget_alert_message,
                "financial_suggestion": financial_suggestion,
            }
        )
    return rows


def financial_health_score(user):
    budgets = list(Budget.objects.select_related("category").filter(user=user))
    exceeded_budgets = [budget for budget in budgets if budget.spent > budget.amount]
    exceeded_count = len(exceeded_budgets)

    if exceeded_count == 0:
        budget_points = 40
    elif exceeded_count == 1:
        budget_points = 30
    else:
        budget_points = 15

    savings_goals = SavingsGoal.objects.filter(user=user, goal_type="savings")
    if savings_goals.exists():
        average_goal_progress = sum(goal.progress for goal in savings_goals) / savings_goals.count()
    else:
        average_goal_progress = 0

    if average_goal_progress >= 80:
        savings_points = 25
    elif average_goal_progress >= 50:
        savings_points = 15
    else:
        savings_points = 5

    emergency_summary = emergency_fund_summary(user)
    emergency_progress = emergency_summary["progress"]
    if emergency_progress >= 80:
        emergency_points = 25
    elif emergency_progress >= 50:
        emergency_points = 15
    else:
        emergency_points = 5

    overspending_penalty = min(exceeded_count * 5, 10)
    score = max(0, min(100, budget_points + savings_points + emergency_points - overspending_penalty))

    if score >= 90:
        status = "🟢 Excellent Financial Health"
        status_class = "excellent"
    elif score >= 70:
        status = "🟡 Good Financial Health"
        status_class = "good"
    elif score >= 50:
        status = "🟠 Needs Improvement"
        status_class = "improve"
    else:
        status = "🔴 Financial Attention Required"
        status_class = "critical"

    if emergency_points == 25:
        top_positive = "Strong Emergency Fund"
    elif budget_points == 40:
        top_positive = "Budgets Within Limit"
    elif savings_points == 25:
        top_positive = "Strong Savings Goal Progress"
    else:
        top_positive = "Active Financial Tracking"

    if exceeded_budgets:
        top_improvement = f"{exceeded_budgets[0].category.name} Budget Exceeded"
    elif emergency_points == 5:
        top_improvement = "Build Emergency Fund"
    elif savings_points == 5:
        top_improvement = "Improve Savings Goal Progress"
    else:
        top_improvement = "Maintain Current Habits"

    return {
        "score": score,
        "status": status,
        "status_class": status_class,
        "top_positive": top_positive,
        "top_improvement": top_improvement,
        "budget_points": budget_points,
        "savings_points": savings_points,
        "emergency_points": emergency_points,
        "overspending_penalty": overspending_penalty,
    }


def smart_dashboard_insights(user, month_start, financial_health):
    month_expenses = Transaction.objects.select_related("category").filter(
        user=user,
        transaction_type="expense",
        date__year=month_start.year,
        date__month=month_start.month,
    )
    total_month_expenses = month_expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    top_category = (
        month_expenses.values("category__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")
        .first()
    )
    highest_spending_category = top_category["category__name"] if top_category else "No expenses yet"
    highest_spending_amount = top_category["total"] if top_category else Decimal("0")
    largest_category_percentage = round((highest_spending_amount / total_month_expenses) * 100) if total_month_expenses else 0

    budget_alerts = []
    for budget in Budget.objects.select_related("category").filter(user=user):
        exceeded_amount = budget.spent - budget.amount
        if exceeded_amount > 0:
            budget_alerts.append({
                "category": budget.category.name,
                "exceeded_amount": exceeded_amount,
                "message": f"{budget.category.name} exceeded by {money(exceeded_amount)}",
            })

    savings_goals = list(SavingsGoal.objects.filter(user=user, goal_type="savings"))
    closest_goal = max(savings_goals, key=lambda goal: goal.progress) if savings_goals else None
    if closest_goal:
        closest_goal_name = closest_goal.name
        closest_goal_progress = closest_goal.progress
    else:
        closest_goal_name = "No savings goal yet"
        closest_goal_progress = 0

    emergency_summary = emergency_fund_summary(user)
    previous_month = shift_month(month_start, -1)
    previous_expenses = Transaction.objects.filter(
        user=user,
        transaction_type="expense",
        date__year=previous_month.year,
        date__month=previous_month.month,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    if total_month_expenses > previous_expenses:
        change = round(((total_month_expenses - previous_expenses) / previous_expenses) * 100) if previous_expenses else 100
        monthly_spending_trend = f"📈 Spending increased by {change}% compared to last month."
    elif total_month_expenses < previous_expenses:
        change = round(((previous_expenses - total_month_expenses) / previous_expenses) * 100) if previous_expenses else 0
        monthly_spending_trend = f"📉 Spending decreased by {change}% compared to last month."
    else:
        monthly_spending_trend = "➡ Spending remained stable compared to last month."

    return {
        "highest_spending_category": highest_spending_category,
        "highest_spending_amount": highest_spending_amount,
        "budget_alerts": budget_alerts,
        "closest_goal": closest_goal_name,
        "closest_goal_progress": closest_goal_progress,
        "emergency_fund_status": emergency_summary["status"],
        "emergency_fund_progress": emergency_summary["progress"],
        "financial_health_score": financial_health["score"],
        "financial_health_status": financial_health["status"],
        "monthly_spending_trend": monthly_spending_trend,
        "largest_category_percentage": largest_category_percentage,
    }


def month_end_surplus_analysis(user, month_start):
    month_qs = Transaction.objects.filter(
        user=user,
        date__year=month_start.year,
        date__month=month_start.month,
    )
    monthly_income = month_qs.filter(transaction_type="income").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    monthly_expenses = month_qs.filter(transaction_type="expense").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    monthly_surplus = monthly_income - monthly_expenses
    emergency_progress = emergency_fund_summary(user)["progress"]

    if monthly_surplus > 0 and emergency_progress < 50:
        emergency_contribution = monthly_surplus * Decimal("0.70")
        goal_contribution = monthly_surplus - emergency_contribution
        recommendation = "Prioritize Emergency Fund"
    elif monthly_surplus > 0:
        goal_contribution = monthly_surplus * Decimal("0.70")
        emergency_contribution = monthly_surplus - goal_contribution
        recommendation = "Prioritize active Savings Goals"
    else:
        emergency_contribution = Decimal("0")
        goal_contribution = Decimal("0")
        recommendation = "No surplus available this month"

    return {
        "monthly_income": monthly_income,
        "monthly_expenses": monthly_expenses,
        "monthly_surplus": monthly_surplus,
        "emergency_contribution": emergency_contribution,
        "goal_contribution": goal_contribution,
        "recommendation": recommendation,
    }


def base_context(active, user, request=None):
    preference = ensure_user_defaults(user)
    month_start = selected_month(request) if request else date(timezone.localdate().year, timezone.localdate().month, 1)
    transactions_qs = Transaction.objects.select_related("category").filter(user=user)
    month_qs = transactions_qs.filter(date__year=month_start.year, date__month=month_start.month)
    total_income = month_qs.filter(transaction_type="income").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    total_expenses = month_qs.filter(transaction_type="expense").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    savings = total_income - total_expenses
    categories = category_rows(user, total_expenses)
    today = timezone.localdate()
    current_month_label = month_start.strftime("%B %Y")
    selected_month_value = month_start.strftime("%Y-%m")
    days_in_month = calendar_lib.monthrange(month_start.year, month_start.month)[1]
    date_range_label = f"{month_start.strftime('%b')} 1 - {month_start.strftime('%b')} {days_in_month}, {month_start.year}"
    period = request.GET.get("period", "monthly") if request else "monthly"
    if period == "daily":
        line_labels = [str(day) for day in range(1, days_in_month + 1)]
        line_data = [
            float(month_qs.filter(transaction_type="expense", date__day=day).aggregate(total=Sum("amount"))["total"] or Decimal("0"))
            for day in range(1, days_in_month + 1)
        ]
    else:
        year_qs = transactions_qs.filter(date__year=month_start.year)
        line_labels = [date(month_start.year, month, 1).strftime("%b") for month in range(1, 13)]
        line_data = [
            float(year_qs.filter(transaction_type="expense", date__month=month).aggregate(total=Sum("amount"))["total"] or Decimal("0"))
            for month in range(1, 13)
        ]
    category_chart_rows = [cat for cat in categories if cat["spent"] > 0]
    emergency_summary = emergency_fund_summary(user)

    currency_symbol = "₹"

    if preference.currency == "USD":
            currency_symbol = "$"
    elif preference.currency == "EUR":
            currency_symbol = "€"

    return {
        
        "active": active,
        "preference": preference,
        "currency_symbol": currency_symbol,
        "total_balance": savings,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "savings": savings,
        "transactions": transaction_rows(month_qs[:20]),
        "categories": categories,
        "budgets": budget_rows(user),
        "goals": user_goal_rows(user),
        "emergency_summary": emergency_summary,
        "chart_json": json.dumps({
            "lineLabels": line_labels,
            "lineData": line_data,
            "categoryLabels": [cat["name"] for cat in category_chart_rows] or ["No expenses yet"],
            "categoryData": [float(cat["spent"]) for cat in category_chart_rows] or [1],
            "categoryColors": [cat["color"] for cat in category_chart_rows] or ["#203753"],
            "goalLabels": [goal["name"] for goal in user_goal_rows(user)] or ["No goals yet"],
            "goalData": [float(goal["saved"]) for goal in user_goal_rows(user)] or [1],
        }),
        "current_month_label": current_month_label,
        "selected_month_value": selected_month_value,
        "selected_period": period,
        "previous_month_value": shift_month(month_start, -1).strftime("%Y-%m"),
        "next_month_value": shift_month(month_start, 1).strftime("%Y-%m"),
        "date_range_label": date_range_label,
        "today_label": today.strftime("%B %d, %Y"),
        "user_display_name": preference.name or user.first_name or user.username,
        "user_initial": (
            preference.name
            or user.first_name
            or user.username
            or "U"
            )[:1].upper(),
        "money": money,
    }


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "tracker/home.html")


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created. Welcome to XpenseTrack!")
            return redirect("dashboard")
    else:
        form = SignUpForm()
    return render(request, "tracker/signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, "Logged in successfully.")
            return redirect(request.GET.get("next") or "dashboard")
    else:
        form = AuthenticationForm(request)
    return render(request, "tracker/login.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("home")


@require_POST
@login_required
def delete_account(request):
    user = request.user
    logout(request)
    user.delete()
    messages.success(request, "Your account has been deleted.")
    return redirect("home")


@login_required
def dashboard(request):
    context = base_context("dashboard", request.user, request)
    month_start = selected_month(request)
    today = timezone.localdate()
    today_transaction_count = Transaction.objects.filter(user=request.user, date=today).count()
    financial_health = financial_health_score(request.user)
    context["financial_health"] = financial_health
    context["today_transaction_count"] = today_transaction_count
    context["daily_reminder_pending"] = context["preference"].daily_expense_reminder_enabled and today_transaction_count == 0
    context["daily_reminder_enabled"] = context["preference"].daily_expense_reminder_enabled
    context["daily_reminder_time"] = context["preference"].daily_expense_reminder_time
    context["surplus_analysis"] = month_end_surplus_analysis(request.user, month_start)
    context.update(smart_dashboard_insights(request.user, month_start, financial_health))
    return render(request, "tracker/dashboard.html", context)


@login_required
def transactions(request):
    context = base_context("transactions", request.user, request)
    month_start = selected_month(request)
    queryset = Transaction.objects.select_related("category").filter(user=request.user, date__year=month_start.year, date__month=month_start.month)
    search = request.GET.get("q", "").strip()
    tx_type = request.GET.get("type", "")
    category_id = request.GET.get("category", "")

    if search:
        queryset = queryset.filter(title__icontains=search)
    if tx_type in {"income", "expense"}:
        queryset = queryset.filter(transaction_type=tx_type)
    if category_id:
        queryset = queryset.filter(category_id=category_id)

    context["transactions"] = transaction_rows(queryset)
    context["search"] = search
    context["selected_type"] = tx_type
    context["selected_category"] = category_id
    return render(request, "tracker/transactions.html", context)


@login_required
def export_transactions(request):
    export_format = request.GET.get("format", "csv")
    month_start = selected_month(request)
    rows = Transaction.objects.select_related("category").filter(user=request.user, date__year=month_start.year, date__month=month_start.month)
    filename_base = f"xpensetrack-{month_start:%Y-%m}"
    if export_format == "pdf":
        response = HttpResponse(content_type="text/html")
        response["Content-Disposition"] = f'attachment; filename="{filename_base}-printable.html"'
        response.write("<h1>XpenseTrack Report</h1><p>Open this file and print/save as PDF.</p><table border='1' cellspacing='0' cellpadding='8'>")
        response.write("<tr><th>Date</th><th>Title</th><th>Category</th><th>Type</th><th>Amount</th><th>Status</th></tr>")
        for item in rows:
            response.write(f"<tr><td>{item.date}</td><td>{item.title}</td><td>{item.category.name}</td><td>{item.transaction_type}</td><td>{item.amount}</td><td>{item.status}</td></tr>")
        response.write("</table>")
        return response
    if export_format == "txt":
        response = HttpResponse(content_type="text/plain")
        response["Content-Disposition"] = f'attachment; filename="{filename_base}.txt"'
        for item in rows:
            response.write(f"{item.date} | {item.title} | {item.category.name} | {item.transaction_type} | {item.amount} | {item.status}\n")
        return response
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename_base}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Date", "Title", "Category", "Type", "Amount", "Status", "Payment Method", "Notes"])
    for item in rows:
        writer.writerow([item.date, item.title, item.category.name, item.transaction_type, item.amount, item.status, item.payment_method, item.notes])
    return response


@login_required
def add_expense(request):
    transaction_id = request.GET.get("edit")
    instance = None
    if transaction_id:
        instance = get_object_or_404(Transaction, pk=transaction_id, user=request.user)

    if request.method == "POST":
        instance = get_object_or_404(Transaction, pk=request.POST["transaction_id"], user=request.user) if request.POST.get("transaction_id") else None
        form = ExpenseForm(request.POST, instance=instance, user=request.user)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            transaction.save()
            messages.success(request, "Transaction saved successfully.")
            return redirect("transactions")
    else:
        form = ExpenseForm(instance=instance, user=request.user)

    context = base_context("add_expense", request.user, request)
    context["form"] = form
    context["editing_transaction"] = instance
    return render(request, "tracker/add_expense.html", context)


@require_POST
@login_required
def delete_transaction(request, pk):
    get_object_or_404(Transaction, pk=pk, user=request.user).delete()
    messages.success(request, "Transaction deleted.")
    return redirect("transactions")


@login_required
def categories(request):
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            messages.success(request, "Category added.")
            return redirect("categories")
    else:
        form = CategoryForm()

    context = base_context("categories", request.user, request)
    context["form"] = form
    return render(request, "tracker/categories.html", context)


@require_POST
@login_required
def delete_category(request, pk):
    category = get_object_or_404(Category, pk=pk, user=request.user)
    if category.transactions.exists():
        messages.error(request, "This category has transactions, so it cannot be deleted yet.")
    else:
        category.delete()
        messages.success(request, "Category deleted.")
    return redirect("categories")


@login_required
def budgets(request):
    instance = get_object_or_404(Budget, pk=request.GET["edit"], user=request.user) if request.GET.get("edit") else None
    if request.method == "POST":
        instance = get_object_or_404(Budget, pk=request.POST["budget_id"], user=request.user) if request.POST.get("budget_id") else None
        form = BudgetForm(request.POST, instance=instance, user=request.user)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.user = request.user
            budget.save()
            messages.success(request, "Budget saved.")
            return redirect("budgets")
    else:
        form = BudgetForm(instance=instance, user=request.user)

    context = base_context("budgets", request.user, request)
    context["form"] = form
    context["editing_budget"] = instance
    return render(request, "tracker/budgets.html", context)


@require_POST
@login_required
def delete_budget(request, pk):
    get_object_or_404(Budget, pk=pk, user=request.user).delete()
    messages.success(request, "Budget deleted.")
    return redirect("budgets")


@login_required
def savings_goals(request):
    instance = get_object_or_404(SavingsGoal, pk=request.GET["edit"], user=request.user) if request.GET.get("edit") else None
    if request.method == "POST":
        instance = get_object_or_404(SavingsGoal, pk=request.POST["goal_id"], user=request.user) if request.POST.get("goal_id") else None
        form = SavingsGoalForm(request.POST, instance=instance)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = request.user
            goal.save()
            messages.success(request, "Savings goal saved.")
            return redirect("savings_goals")
    else:
        form = SavingsGoalForm(instance=instance)

    context = base_context("savings_goals", request.user, request)
    context["form"] = form
    context["editing_goal"] = instance
    return render(request, "tracker/savings_goals.html", context)


@require_POST
@login_required
def delete_goal(request, pk):
    get_object_or_404(SavingsGoal, pk=pk, user=request.user).delete()
    messages.success(request, "Savings goal deleted.")
    return redirect("savings_goals")


@login_required
def reports(request):
    context = base_context("reports", request.user, request)
    month_start = selected_month(request)
    best_income = Transaction.objects.filter(user=request.user, transaction_type="income").order_by("-amount").first()
    context["best_saving_day"] = best_income.date.strftime("%B %d, %Y") if best_income else "No income yet"
    context["best_saving_amount"] = best_income.amount if best_income else Decimal("0")
    context["surplus_analysis"] = month_end_surplus_analysis(request.user, month_start)
    return render(request, "tracker/reports.html", context)


@login_required
def calendar(request):
    context = base_context("calendar", request.user, request)
    today = timezone.localdate()
    month_start = selected_month(request)
    month_transactions = Transaction.objects.select_related("category").filter(user=request.user, date__year=today.year, date__month=today.month)
    by_day = {}
    for item in month_transactions:
        by_day.setdefault(item.date.day, []).append(item)
    first_weekday, days_in_month = calendar_lib.monthrange(today.year, today.month)
    start_offset = (first_weekday + 1) % 7
    cells = []
    previous_month_days = calendar_lib.monthrange(today.year if today.month > 1 else today.year - 1, today.month - 1 or 12)[1]
    for i in range(start_offset):
        cells.append({"day": previous_month_days - start_offset + i + 1, "muted": True, "items": [], "income": 0, "expense": 0})
    for day in range(1, days_in_month + 1):
        items = by_day.get(day, [])
        income = sum(item.amount for item in items if item.transaction_type == "income")
        expense = sum(item.amount for item in items if item.transaction_type == "expense")
        cells.append({"day": day, "muted": False, "selected": day == today.day, "items": items, "income": income, "expense": expense})
    next_day = 1
    while len(cells) % 7:
        cells.append({"day": next_day, "muted": True, "items": [], "income": 0, "expense": 0})
        next_day += 1
    selected_transactions = month_transactions.filter(date=today)
    selected_income = selected_transactions.filter(transaction_type="income").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    selected_expense = selected_transactions.filter(transaction_type="expense").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    context["calendar_cells"] = cells
    context["selected_day_transactions"] = transaction_rows(selected_transactions)
    context["selected_income"] = selected_income
    context["selected_expense"] = selected_expense
    context["selected_net"] = selected_income - selected_expense
    context["month_name"] = month_start.strftime("%B %Y")
    return render(request, "tracker/calendar.html", context)

@login_required
def settings_view(request):
    preference = ensure_user_defaults(request.user)

    active_tab = request.GET.get("tab", "profile")

    if active_tab not in {"profile", "preferences", "security", "notifications", "danger"}:
        active_tab = "profile"

    
    if request.method == "POST":
        print("ACTION =", request.POST.get("settings_action"))
        print("\n====================")
        print("POST RECEIVED")
        print(request.POST)
        print("====================\n")

        if request.POST.get("settings_action") == "password":

            form = PreferenceForm(instance=preference)
            password_form = PasswordChangeForm(request.user, request.POST)

            print("PASSWORD FORM VALID:", password_form.is_valid())

            if not password_form.is_valid():
                print("PASSWORD ERRORS:", password_form.errors)

            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)

                messages.success(request, "Password updated.")

                return redirect(f"{request.path}?tab=security")

        else:

            form = PreferenceForm(request.POST, instance=preference)
            password_form = PasswordChangeForm(request.user)

            print("FORM VALID:", form.is_valid())

            if not form.is_valid():
                print("FORM ERRORS:")
                print(form.errors)

            if form.is_valid():

                preference = form.save()

                request.user.first_name = preference.name
                request.user.email = preference.email

                request.user.save(
                    update_fields=[
                        "first_name",
                        "email",
                    ]
                )

                messages.success(request, "Settings saved.")

                return redirect(f"{request.path}?tab={active_tab}")

    else:

        form = PreferenceForm(instance=preference)
        password_form = PasswordChangeForm(request.user)

    context = base_context(
        "settings",
        request.user,
        request,
    )

    context["form"] = form
    context["password_form"] = password_form
    context["active_settings_tab"] = active_tab

    print("CONTEXT PREFERENCE =", preference.name)
    print("FORM INITIAL =", form["name"].value())
    return render(
        request,
        "tracker/settings.html",
        context,
    )