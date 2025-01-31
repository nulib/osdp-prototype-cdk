import json

def handler(event, context):
    row = event.get("row", {})
    
    print(f"Processing row: {row}")

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Processed successfully", "row": row}),
    }