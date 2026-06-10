from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("signup/", views.signup_view, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("delete-account/", views.delete_account, name="delete_account"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("transactions/", views.transactions, name="transactions"),
    path("transactions/export/", views.export_transactions, name="export_transactions"),
    path("transactions/<int:pk>/delete/", views.delete_transaction, name="delete_transaction"),
    path("add-expense/", views.add_expense, name="add_expense"),
    path("categories/", views.categories, name="categories"),
    path("categories/<int:pk>/delete/", views.delete_category, name="delete_category"),
    path("budgets/", views.budgets, name="budgets"),
    path("budgets/<int:pk>/delete/", views.delete_budget, name="delete_budget"),
    path("savings-goals/", views.savings_goals, name="savings_goals"),
    path("savings-goals/<int:pk>/delete/", views.delete_goal, name="delete_goal"),
    path("reports/", views.reports, name="reports"),
    path("calendar/", views.calendar, name="calendar"),
    path("settings/", views.settings_view, name="settings"),
]
