#!/usr/bin/env python3
import os

import aws_cdk as cdk

from splitleh_cloud.paths import setup_import_paths

setup_import_paths()

from splitleh_cloud.bundle import ensure_bundled
from splitleh_cloud.splitleh_stack import SplitlehStack

ensure_bundled()

app = cdk.App()
env_name = app.node.try_get_context("env") or "dev"

SplitlehStack(
    app,
    f"SplitlehStack-{env_name}",
    env_name=env_name,
    alert_email=app.node.try_get_context("alert_email"),
    bot_token=app.node.try_get_context("bot_token"),
    webhook_secret=app.node.try_get_context("webhook_secret"),
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION", "ap-southeast-1"),
    ),
)

app.synth()
