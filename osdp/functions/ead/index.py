import json
import os
import boto3
import xml.etree.ElementTree as ET
from datetime import datetime

BUCKET = os.environ["BUCKET"]
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "iiif/")

def extract_metadata_from_xml(xml_content):
    """
    Extract metadata from EAD XML content and create a structured JSON object
    """
    # Parse XML content
    try:
        root = ET.fromstring(xml_content)
        # Create namespace mapping for easier XPath queries
        namespaces = {'ead': 'urn:isbn:1-931666-22-9'}
        
        # Extract key metadata
        result = {}
        
        # Document ID
        eadid = root.find('.//ead:eadid', namespaces)
        result['id'] = eadid.text if eadid is not None else "unknown"
        
        # Title
        title = root.find('.//ead:archdesc/ead:did/ead:unittitle', namespaces)
        result['title'] = title.text if title is not None else ""
        
        # Date range
        unitdate = root.find('.//ead:archdesc/ead:did/ead:unitdate', namespaces)
        if unitdate is not None:
            result['dateRange'] = unitdate.text
            if 'normal' in unitdate.attrib:
                result['normalizedDate'] = unitdate.attrib['normal']
        
        # Abstract/description
        abstract = root.find('.//ead:archdesc/ead:did/ead:abstract', namespaces)
        result['abstract'] = abstract.text if abstract is not None else ""
        
        # Repository info
        repository = root.find('.//ead:archdesc/ead:did/ead:repository/ead:corpname', namespaces)
        result['repository'] = repository.text if repository is not None else ""
        
        # Access restrictions
        access_restrict = root.find('.//ead:archdesc/ead:accessrestrict/ead:p', namespaces)
        result['accessRestrictions'] = access_restrict.text if access_restrict is not None else ""
        
        # Extract collection contents/items
        items = []
        for c01 in root.findall('.//ead:dsc/ead:c01', namespaces):
            item = {}
            item_title = c01.find('./ead:did/ead:unittitle', namespaces)
            item_date = c01.find('./ead:did/ead:unitdate', namespaces)
            
            item['title'] = item_title.text if item_title is not None else ""
            item['date'] = item_date.text if item_date is not None else ""
            
            if item_date is not None and 'normal' in item_date.attrib:
                item['normalizedDate'] = item_date.attrib['normal']
                
            items.append(item)
        
        result['items'] = items
        
        # Add processing metadata
        result['processingDate'] = datetime.now().isoformat()
        
        return result
        
    except Exception as e:
        print(f"Error parsing XML: {e}")
        return {"error": f"Failed to parse XML: {str(e)}"}

def handler(event, _context):
    print(f"Received event: {json.dumps(event)}")
    
    # Get the S3 object key from the event
    if 'key' not in event or 'bucket' not in event:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Missing required parameters 'bucket' and 'key' in event."})
        }
    
    source_bucket = event['bucket']
    source_key = event['key']
    
    try:
        # Download the XML file from S3
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket=source_bucket, Key=source_key)
        xml_content = response['Body'].read().decode('utf-8')
        
        # Process the XML content
        json_data = extract_metadata_from_xml(xml_content)
        
        # Generate output key - preserve part of the original hierarchy but with json extension
        filename = os.path.basename(source_key).replace('.xml', '.json')
        output_key = f"{OUTPUT_PREFIX}{filename}"
        
        # Write the JSON to S3
        s3.put_object(
            Bucket=BUCKET,
            Key=output_key,
            Body=json.dumps(json_data, ensure_ascii=False),
            ContentType="application/json"
        )
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Successfully processed EAD XML and saved JSON",
                "source": f"{source_bucket}/{source_key}",
                "destination": f"{BUCKET}/{output_key}"
            })
        }
        
    except Exception as e:
        print(f"Error processing file {source_key} from bucket {source_bucket}: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Error processing EAD file",
                "error": str(e),
                "source": f"{source_bucket}/{source_key}"
            })
        }