from aws_cdk import CfnOutput, Stack
from constructs import Construct

from splitleh_cloud.constructs.api import Api
from splitleh_cloud.constructs.budget import Budget
from splitleh_cloud.constructs.runtime import Runtime
from splitleh_cloud.constructs.parameter_store import ParameterStore
from splitleh_cloud.constructs.storage import Storage
from splitleh_cloud.paths import setup_import_paths

setup_import_paths()

from splitleh_ocr.cdk import Ocr
from splitleh_telegram.cdk import Telegram


class SplitlehStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        alert_email: str | None = None,
        bot_token: str | None = None,
        webhook_secret: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        secrets = ParameterStore(
            self, "ParameterStore", env_name=env_name,
            bot_token=bot_token, webhook_secret=webhook_secret,
        )
        storage = Storage(self, "Storage", env_name=env_name)
        api = Api(self, "Api", env_name=env_name)
        runtime = Runtime(
            self, "Runtime", env_name=env_name,
            table=storage.table, bucket=storage.bucket,
        )

        ocr = Ocr(self, "Ocr", runtime=runtime)
        telegram = Telegram(
            self, "Telegram", runtime=runtime,
            ocr_function=ocr.function,
            bot_token_param=secrets.bot_token,
            webhook_param=secrets.webhook,
        )
        api.add_webhook_route(telegram_fn=telegram.function)

        if alert_email:
            Budget(self, "Budget", alert_email=alert_email)

        CfnOutput(self, "WebhookUrl", value=f"{api.api_url}telegram/webhook")
        CfnOutput(self, "WebhookSecretParamName", value=secrets.webhook_secret_name)
        CfnOutput(self, "BotTokenParamName", value=secrets.bot_token_param_name)
        CfnOutput(self, "SessionsTableName", value=storage.table.table_name)
        CfnOutput(self, "ReceiptsBucketName", value=storage.bucket.bucket_name)
        CfnOutput(self, "TelegramFunctionName", value=telegram.function.function_name)
