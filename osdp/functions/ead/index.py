import json
import os
import boto3
from eadpy import Ead
import uuid

s3 = boto3.client('s3')

def handler(event, context):
    print(f"Processing Ead: {event}")
    
    # Get bucket and key from event
    bucket = event.get('bucket')
    key = event.get('key')
    
    if not bucket or not key:
        print("Missing required parameters: bucket or key")
        return {
            'statusCode': 400,
            'body': json.dumps('Missing required parameters: bucket or key')
        }
    
    output_prefix = os.environ.get('OUTPUT_PREFIX', 'iiif/')
    
    try:
        # Download the Ead XML file from S3
        # response = s3.get_object(Bucket=bucket, Key=key)
        # ead_content = response['Body'].read().decode('utf-8')

        # Changed: Use the correct /tmp directory path and store the full path
        local_file_name = f"/tmp/{uuid.uuid4().hex}.xml"
        s3.download_file(bucket, key, local_file_name)
        print(f"Downloaded file to: {local_file_name}")
        
        # Parse the Ead XML using eadpy with the exact same path
        ead = Ead(local_file_name)
        
        parsed_ead = ead.create_item_chunks()
        for record in parsed_ead:
            text = record['text']
            print("Embedding Text:")
            for line in text.split('\n'):
                print(f"  {line}")
            print("-" * 20)
        
        # Save the processed data back to S3
        output_key = f"{output_prefix}{os.path.basename(key).replace('.xml', '.json')}"
        s3.put_object(
            Bucket=bucket,
            Key=output_key,
            Body=json.dumps(parsed_ead, indent=2),
            ContentType='application/json'
        )
        
        print(f"Successfully processed Ead file. Output saved to s3://{bucket}/{output_key}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Ead file processed successfully',
                'source': f"s3://{bucket}/{key}",
                'destination': f"s3://{bucket}/{output_key}"
            })
        }
        
    except Exception as e:
        print(f"Error processing Ead file: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error processing Ead file: {str(e)}')
        }