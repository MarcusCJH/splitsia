from aws_cdk import aws_ssm as ssm
from constructs import Construct


class ParameterStore(Construct):
    """Bot token + webhook secret in SSM Parameter Store (free standard tier)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        bot_token: str | None = None,
        webhook_secret: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        bot_name = f"/splitleh/telegram/bot_token_{env_name}"
        if bot_token:
            self.bot_token = ssm.StringParameter(
                self,
                "BotToken",
                parameter_name=bot_name,
                string_value=bot_token,
                description="Telegram bot token from @BotFather",
            )
        else:
            self.bot_token = ssm.StringParameter.from_string_parameter_name(
                self, "BotToken", bot_name
            )
        self.bot_token_param_name = bot_name

        webhook_name = f"/splitleh/telegram/webhook_secret_{env_name}"
        if webhook_secret:
            self.webhook = ssm.StringParameter(
                self,
                "WebhookSecret",
                parameter_name=webhook_name,
                string_value=webhook_secret,
                description="Telegram setWebhook secret_token",
            )
        else:
            self.webhook = ssm.StringParameter.from_string_parameter_name(
                self, "WebhookSecret", webhook_name
            )
        self.webhook_secret_name = webhook_name
