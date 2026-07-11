import os
from types import SimpleNamespace

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def lambda_context():
    return SimpleNamespace(
        function_name="test-function",
        memory_limit_in_mb=256,
        invoked_function_arn="arn:aws:lambda:ap-southeast-1:123456789012:function:test",
        aws_request_id="test-request-id",
    )


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SPLITLEH_SESSIONS_TABLE", "splitleh_sessions_test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    import shared.split_store as split_store

    split_store._table = None
    yield
    split_store._table = None


@pytest.fixture
def dynamodb_table():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="ap-southeast-1")
        resource.create_table(
            TableName=os.environ["SPLITLEH_SESSIONS_TABLE"],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield resource.Table(os.environ["SPLITLEH_SESSIONS_TABLE"])
