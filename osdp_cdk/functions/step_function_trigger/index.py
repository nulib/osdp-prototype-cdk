import os
import json
import boto3

sfn = boto3.client('stepfunctions')

def handler(event, context):
    # Debugging logs
    print(f"Triggering Step Function with Bucket: {os.environ['BUCKET']}, Key: {os.environ['KEY']}")

    execution_input = json.dumps({
        "collection_url": os.environ["COLLECTION_URL"],
        "s3": {
            "Bucket": os.environ["BUCKET"],
            "Key": os.environ["KEY"]
        }
    })

    sfn.start_execution(
        stateMachineArn=os.environ['STATE_MACHINE_ARN'],
        name='CDKTriggeredExecution',
        input=execution_input
    )

    # return {
    #     "statusCode": 200,
    #     "body": json.dumps({"message": "Step Function triggered", "response": response})
    # }