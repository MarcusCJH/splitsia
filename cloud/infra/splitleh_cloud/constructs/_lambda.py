from __future__ import annotations

from typing import Sequence

from aws_cdk import Duration
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from splitleh_cloud.constructs.runtime import Runtime
from splitleh_cloud.lambda_runtime import LAMBDA_ARCHITECTURE, LAMBDA_RUNTIME
from splitleh_cloud.paths import lambda_code_dir, lambda_handler


class BaseLambda(Construct):
    """
    Reusable L3 - one service slug → one Lambda.

    Asset zip is flat: lambda_function.handler at root (see bundle_lambda.py).
    """

    function: lambda_.Function

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        slug: str,
        runtime: Runtime,
        timeout: Duration,
        memory_size: int = 256,
        environment: dict[str, str] | None = None,
        parameters: Sequence[ssm.IStringParameter] = (),
        policy_statements: Sequence[iam.PolicyStatement] = (),
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.function = lambda_.Function(
            self,
            "Function",
            function_name=slug,
            handler=lambda_handler(),
            runtime=LAMBDA_RUNTIME,
            architecture=LAMBDA_ARCHITECTURE,
            code=lambda_.Code.from_asset(str(lambda_code_dir(slug))),
            layers=[runtime.layer],
            timeout=timeout,
            memory_size=memory_size,
            environment={**runtime.base_env(), **(environment or {})},
        )

        runtime.grant_data_access(self.function)
        for param in parameters:
            param.grant_read(self.function)
        for statement in policy_statements:
            self.function.add_to_role_policy(statement)
