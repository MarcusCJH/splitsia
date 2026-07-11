from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct

from splitleh_cloud.lambda_runtime import (
    LAMBDA_ARCHITECTURE,
    LAMBDA_COMPATIBLE_RUNTIMES,
)
from splitleh_cloud.paths import LAMBDA_LAYER, LAYER_VERSION_NAME


class Runtime(Construct):
    """Shared Lambda layer + common env for API services."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        table: dynamodb.ITable,
        bucket: s3.IBucket,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        self.table = table
        self.bucket = bucket

        self.layer = lambda_.LayerVersion(
            self,
            "Layer",
            layer_version_name=LAYER_VERSION_NAME,
            code=lambda_.Code.from_asset(str(LAMBDA_LAYER)),
            compatible_runtimes=LAMBDA_COMPATIBLE_RUNTIMES,
            compatible_architectures=[LAMBDA_ARCHITECTURE],
            description="SplitLeh API Python dependencies",
        )

    def base_env(self) -> dict[str, str]:
        return {
            "SPLITLEH_SESSIONS_TABLE": self.table.table_name,
            "SPLITLEH_RECEIPTS_BUCKET": self.bucket.bucket_name,
            "SPLITLEH_ENV": self.env_name,
            "SPLITLEH_BEDROCK_MODEL_ID": "apac.amazon.nova-lite-v1:0",
        }

    def grant_data_access(self, fn: lambda_.IFunction) -> None:
        self.table.grant_read_write_data(fn)
        self.bucket.grant_read_write(fn)
