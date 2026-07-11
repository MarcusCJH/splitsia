from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from constructs import Construct


class Storage(Construct):
    """DynamoDB sessions table + short-lived S3 bucket for receipt uploads."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.table = dynamodb.Table(
            self,
            "SessionsTable",
            table_name=f"splitleh_sessions_{env_name}",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.bucket = s3.Bucket(
            self,
            "ReceiptsBucket",
            bucket_name=f"splitleh-receipts-{env_name}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(expiration=Duration.days(1), enabled=True),
            ],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
