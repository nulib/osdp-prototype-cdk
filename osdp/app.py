#!/usr/bin/env python3
import os
import sys

import aws_cdk as cdk
from pipeline.pipeline_stack import PipelineStack
from stacks.osdp_prototype_stack import OsdpPrototypeStack

# Initialize the CDK app which loads the built-in context (from cdk.json and CLI)
app = cdk.App()

# All the required context keys
required_context = ["collection_url", "embedding_model_arn"]

# Validate that each required context is provided
for key in required_context:
    value = app.node.try_get_context(key)
    if not value:
        sys.exit(
            f"Error: Missing required context variable '{key}'. "
            f"Please pass it via the CLI (e.g., -c {key}=your_value) or define it in cdk.json."
        )

# Try to get a stack prefix value from the env or CDK context (CLI or cdk.json)
stack_prefix = os.environ.get("DEV_PREFIX") or app.node.try_get_context("stack_prefix")

if not stack_prefix:
    print("No stack_prefix found in CDK context. Exiting.")
    print("Please set using the cli.")
    print("Example: cdk deploy -c stack_prefix=alice")
    exit(1)


OsdpPrototypeStack(
    app,
    f"{stack_prefix}-OSDP-Prototype",
    stack_prefix=stack_prefix,
    # If you don't specify 'env', this stack will be environment-agnostic.
    # Account/Region-dependent features and context lookups will not work,
    # but a single synthesized template can be deployed anywhere.
    # Uncomment the next line to specialize this stack for the AWS Account
    # and Region that are implied by the current CLI configuration.
    env=cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION")),
    # Uncomment the next line if you know exactly what Account and Region you
    # want to deploy the stack to. */
    # env=cdk.Environment(account='123456789012', region='us-east-1'),
    # For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html
)
PipelineStack(
    app, "OsdpPipelineStack", stack_prefix="staging", env=cdk.Environment(account="625046682746", region="us-east-1")
)
app.synth()
