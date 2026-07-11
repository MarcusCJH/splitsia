"""Telegram Lambda CDK - service-specific timeout, memory, env, IAM."""

from aws_cdk import Duration
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from splitleh_cloud.constructs._lambda import BaseLambda
from splitleh_cloud.constructs.runtime import Runtime

SERVICE = "splitleh_telegram"


class Telegram(BaseLambda):
    """Telegram webhook handler."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        runtime: Runtime,
        ocr_function: lambda_.IFunction,
        bot_token_param: ssm.IStringParameter,
        webhook_param: ssm.IStringParameter,
        **kwargs,
    ) -> None:
        super().__init__(
            scope,
            construct_id,
            slug=SERVICE,
            runtime=runtime,
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "SPLITLEH_OCR_FUNCTION": ocr_function.function_name,
                "TELEGRAM_BOT_TOKEN_PARAM_NAME": bot_token_param.parameter_name,
                "TELEGRAM_WEBHOOK_SECRET_PARAM_NAME": webhook_param.parameter_name,
            },
            parameters=[bot_token_param, webhook_param],
            policy_statements=[
                iam.PolicyStatement(
                    actions=["lambda:InvokeFunction"],
                    resources=[ocr_function.function_arn],
                ),
            ],
            **kwargs,
        )
