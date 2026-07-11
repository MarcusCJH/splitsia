"""ARN helpers for cross-Lambda IAM."""

from aws_cdk import ArnFormat, Stack
from constructs import Construct


def lambda_function_arn(scope: Construct, function_name: str) -> str:
    return Stack.of(scope).format_arn(
        service="lambda",
        resource="function",
        resource_name=function_name,
        arn_format=ArnFormat.COLON_RESOURCE_NAME,
    )
