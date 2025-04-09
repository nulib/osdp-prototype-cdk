#!/usr/bin/env python3
import os
import sys
import tomllib

import aws_cdk as cdk
from pipeline.pipeline_stack import PipelineStack
from stacks.osdp_prototype_stack import OsdpPrototypeStack

# Initialize the CDK app which loads the built-in context (from cdk.json and CLI)
app = cdk.App()

# Load TOML configuration from config.toml
# This file should be in the same directory as this script
config_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.toml")
print(f"Looking for config file at: {config_file_path}")

if config_file_path:
    try:
        with open(config_file_path, "rb") as f:
            config = tomllib.load(f)

            # Add config values to context
            for key, value in config.items():
                app.node.set_context(key, value)
    except FileNotFoundError:
        sys.exit(f"Error: Config file '{config_file_path}' not found.")
    except tomllib.TOMLDecodeError:
        sys.exit(f"Error: Config file '{config_file_path}' contains invalid TOML.")
else:
    sys.exit(f"Error: Config file '{config_file_path}' not found.")

# All the required context keys
required_context = ["embedding_model_arn", "foundation_model_arn", "data"]

# Validate that each required context is provided
for key in required_context:
    value = app.node.try_get_context(key)
    if not value:
        sys.exit(
            f"Error: Missing required context variable '{key}'. "
            f"Please pass it via the CLI (e.g., -c {key}=your_value) or define it in cdk.json."
        )

# Validate the data structure
data = app.node.try_get_context("data")
data_type = data.get("type")
if data_type not in ["iiif", "ead"]:
    sys.exit(f"Error: Invalid data type '{data_type}'. The data.type must be either 'iiif' or 'ead'.")

if data_type == "iiif" and not data.get("collection_url"):
    sys.exit(
        "Error: Missing required field 'collection_url' for data type 'iiif'. "
        "Please provide it in the 'data' context object."
    )

if data_type == "ead":
    s3_config = data.get("s3", {})
    if not s3_config.get("bucket") or not s3_config.get("prefix"):
        sys.exit(
            "Error: Missing required S3 configuration for data type 'ead'. "
            "Please provide 'bucket' and 'prefix' in the 'data.s3' context object."
        )

# Try to get a stack prefix value from the env or the config file
# For NU developers this will use or DEV_PREFIX env var
stack_prefix = app.node.try_get_context("stack_prefix") or os.environ.get("DEV_PREFIX")

if not stack_prefix:
    print("No stack_prefix found in CDK context or environment. Exiting.")
    print("Please set stack prefix in the config.toml file.")
    exit(1)

# Set the stack_prefix in context so constructs can access it without direct passing
app.node.set_context("stack_prefix", stack_prefix)

OsdpPrototypeStack(
    app,
    f"{stack_prefix}-OSDP-Prototype",
    env=cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION")),
    # Uncomment the next line to specialize this stack for the AWS Account
    # and Region that are implied by the current CLI configuration.
    # env=cdk.Environment(account='123456789012', region='us-east-1'),
    # For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html
)

PipelineStack(app, "OsdpPipelineStack", env=cdk.Environment(account="625046682746", region="us-east-1"))
app.synth()
