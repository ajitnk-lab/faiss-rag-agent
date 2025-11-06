#!/usr/bin/env python3
"""
Transform classifier CSV to JSON format for FAISS embeddings.
Reads from S3, transforms data, outputs JSON for embedding generation.
"""
import boto3
import csv
import json
import sys
from io import StringIO

def transform_csv_to_json(bucket_name, csv_key, output_file, limit=None):
    """
    Transform CSV from S3 to JSON format for embeddings.
    
    Args:
        bucket_name: S3 bucket containing CSV
        csv_key: S3 key for CSV file
        output_file: Local path to save JSON
        limit: Optional limit for MVP testing (e.g., 10 repos)
    """
    s3 = boto3.client('s3')
    
    print(f"📥 Downloading CSV from s3://{bucket_name}/{csv_key}")
    response = s3.get_object(Bucket=bucket_name, Key=csv_key)
    csv_content = response['Body'].read().decode('utf-8')
    
    csv_reader = csv.DictReader(StringIO(csv_content))
    
    documents = []
    for idx, row in enumerate(csv_reader):
        if limit and idx >= limit:
            break
            
        # Build rich text for embedding
        text_parts = [
            f"Repository: {row.get('repository', 'Unknown')}",
            f"Description: {row.get('description', 'No description')}",
            f"Solution Type: {row.get('solution_type', 'Unknown')}",
            f"Competency: {row.get('competency', 'Unknown')}",
            f"Primary Language: {row.get('primary_language', 'Unknown')}",
            f"AWS Services: {row.get('aws_services', 'Unknown')}",
            f"Topics: {row.get('topics', 'None')}",
        ]
        
        text = " | ".join(text_parts)
        
        # Preserve all metadata
        metadata = {
            'repository': row.get('repository', ''),
            'description': row.get('description', ''),
            'solution_type': row.get('solution_type', ''),
            'competency': row.get('competency', ''),
            'customer_problems': row.get('customer_problems', ''),
            'solution_marketing': row.get('solution_marketing', ''),
            'primary_language': row.get('primary_language', ''),
            'secondary_language': row.get('secondary_language', ''),
            'aws_services': row.get('aws_services', ''),
            'deployment_tools': row.get('deployment_tools', ''),
            'cost_range': row.get('cost_range', ''),
            'setup_time': row.get('setup_time', ''),
            'usp': row.get('usp', ''),
            'freshness_status': row.get('freshness_status', ''),
            'stars': row.get('stars', '0'),
            'topics': row.get('topics', ''),
            'url': row.get('url', ''),
        }
        
        documents.append({
            'id': f"repo_{idx}",
            'text': text,
            'metadata': metadata
        })
    
    # Save to JSON
    with open(output_file, 'w') as f:
        json.dump(documents, f, indent=2)
    
    print(f"✅ Transformed {len(documents)} repositories")
    print(f"💾 Saved to {output_file}")
    
    return documents

if __name__ == '__main__':
    # Default: aws-samples bucket with 10 repos for MVP
    bucket = 'aws-github-repo-classification-aws-samples'
    csv_key = 'results/classification_results.csv'
    output = '/persistent/home/ubuntu/workspace/faiss-rag-agent/data/repos_mvp.json'
    
    if len(sys.argv) > 1:
        limit = int(sys.argv[1])
    else:
        limit = 10  # MVP: 10 repos
    
    transform_csv_to_json(bucket, csv_key, output, limit=limit)
