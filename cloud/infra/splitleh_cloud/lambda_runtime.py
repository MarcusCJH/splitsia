from aws_cdk import aws_lambda as lambda_

from splitleh_cloud.paths import LAMBDA_PYTHON

LAMBDA_RUNTIME = lambda_.Runtime(f"python{LAMBDA_PYTHON}")
LAMBDA_ARCHITECTURE = lambda_.Architecture.ARM_64
LAMBDA_COMPATIBLE_RUNTIMES = [LAMBDA_RUNTIME]
