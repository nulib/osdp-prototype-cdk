import json
import os
import uuid

import boto3

sfn = boto3.client("stepfunctions")


def handler(event, context):
    # Get environment variables
    workflow_type = os.environ.get("WORKFLOW_TYPE", "iiif")
    
    # Allow overriding workflow type from the event
    if event and isinstance(event, dict) and "workflowType" in event:
        workflow_type = event["workflowType"]
        
    # Debugging logs
    print(f"Triggering Step Function with workflow type: {workflow_type}")
    print(f"Bucket: {os.environ['BUCKET']}")
    
    # Common parameters
    execution_input = {
        "s3": {"Bucket": os.environ["BUCKET"]},
        "workflowType": workflow_type,
    }
    
    # Add workflow-specific parameters
    if workflow_type == "iiif":
        execution_input["collection_url"] = os.environ["SOURCE"]
        execution_input["s3"]["Key"] = os.environ["KEY"]
    elif workflow_type == "ead":
        # Use XML prefix for EAD workflow
        s3Location = os.environ["SOURCE"]
        execution_input["s3"]["Prefix"] = s3Location.get("prefix")
    
    # Generate a unique name for this execution
    execution_name = f"{workflow_type}-{uuid.uuid4().hex[:8]}"
    
    # Start the execution
    response = sfn.start_execution(
        stateMachineArn=os.environ["STATE_MACHINE_ARN"],
        name=execution_name,
        input=json.dumps(execution_input)
    )
    
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": f"{workflow_type.upper()} workflow triggered",
            "executionArn": response["executionArn"],
            "executionName": execution_name,
            "startDate": response["startDate"].isoformat()
        })
    }
