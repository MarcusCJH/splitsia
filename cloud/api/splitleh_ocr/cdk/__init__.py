"""OCR Lambda CDK - service-specific timeout, memory, env, IAM."""

from aws_cdk import Duration
from aws_cdk import aws_iam as iam
from constructs import Construct

from splitleh_cloud.arns import lambda_function_arn
from splitleh_cloud.constructs._lambda import BaseLambda
from splitleh_cloud.constructs.runtime import Runtime

SERVICE = "splitleh_ocr"
TELEGRAM_FUNCTION = "splitleh_telegram"


class Ocr(BaseLambda):
    """Textract AnalyzeExpense primary; Bedrock Nova optional fallback."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        runtime: Runtime,
        **kwargs,
    ) -> None:
        super().__init__(
            scope,
            construct_id,
            slug=SERVICE,
            runtime=runtime,
            timeout=Duration.seconds(120),
            memory_size=512,
            environment={"SPLITLEH_TELEGRAM_FUNCTION": TELEGRAM_FUNCTION},
            policy_statements=[
                iam.PolicyStatement(
                    actions=["textract:AnalyzeExpense"],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    actions=["bedrock:InvokeModel", "bedrock:Converse"],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    actions=["lambda:InvokeFunction"],
                    resources=[lambda_function_arn(scope, TELEGRAM_FUNCTION)],
                ),
            ],
            **kwargs,
        )
