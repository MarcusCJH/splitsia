from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_lambda as lambda_
from constructs import Construct


class Api(Construct):
    """HTTP API v2 - Telegram webhook."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.http_api = apigwv2.HttpApi(
            self,
            "HttpApi",
            api_name=f"splitleh_api_{env_name}",
        )
        self.api_url = self.http_api.url

    def add_webhook_route(self, *, telegram_fn: lambda_.IFunction) -> None:
        integration = integrations.HttpLambdaIntegration(
            "TelegramWebhookIntegration",
            telegram_fn,
        )
        self.http_api.add_routes(
            path="/telegram/webhook",
            methods=[apigwv2.HttpMethod.POST],
            integration=integration,
        )
