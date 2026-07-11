from aws_cdk import aws_budgets as budgets
from constructs import Construct


class Budget(Construct):
    """Monthly AWS cost budget with email alerts at 80% and 100%."""

    def __init__(self, scope: Construct, construct_id: str, *, alert_email: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        budgets.CfnBudget(
            self,
            "MonthlyCap",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name="splitleh_monthly_cap",
                budget_limit=budgets.CfnBudget.SpendProperty(amount=10, unit="USD"),
                budget_type="COST",
                time_unit="MONTHLY",
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        comparison_operator="GREATER_THAN",
                        notification_type="ACTUAL",
                        threshold=threshold,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            address=alert_email,
                            subscription_type="EMAIL",
                        ),
                    ],
                )
                for threshold in (80, 100)
            ],
        )
