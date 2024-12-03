#!/usr/bin/env python3
import os
import sys
import json
import time
import boto3
import requests
import argparse
from pathlib import Path

def create_test_files(test_dir: str, num_files: int = 5):
    """Create sample test files"""
    Path(test_dir).mkdir(parents=True, exist_ok=True)
    
    for i in range(num_files):
        file_path = Path(test_dir) / f"test_doc_{i+1}.txt"
        with open(file_path, "w") as f:
            f.write(f"Test Document {i+1}\nThis is a test document for the Document AI Pipeline.\nCreated at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Created test file: {file_path}")

def upload_test_files(local_dir: str, bucket: str, s3_prefix: str):
    """Upload test files to S3"""
    s3 = boto3.client('s3')
    
    uploaded_count = 0
    # Upload each file in the directory
    for file_path in Path(local_dir).glob('*'):
        if file_path.is_file():
            s3_key = f"{s3_prefix}/{file_path.name}"
            print(f"Uploading {file_path} to s3://{bucket}/{s3_key}")
            s3.upload_file(str(file_path), bucket, s3_key)
            uploaded_count += 1
    
    print(f"Uploaded {uploaded_count} files to S3")
    return uploaded_count

def trigger_processing(api_url: str, directory: str):
    """Trigger the processing pipeline"""
    payload = {
        "directory": directory
    }
    
    print(f"Triggering processing for directory: {directory}")
    try:
        response = requests.post(
            api_url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=10
        )
        
        response.raise_for_status()
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.json()}")
        return response.json().get('executionArn')  # Return Step Function execution ARN
    except requests.exceptions.RequestException as e:
        print(f"Error triggering processing: {str(e)}")
        sys.exit(1)

def wait_for_results(bucket: str, s3_prefix: str, num_files: int, timeout: int = 300):
    """Wait for processed results to appear in S3"""
    s3 = boto3.client('s3')
    start_time = time.time()
    
    while (time.time() - start_time) < timeout:
        try:
            response = s3.list_objects_v2(
                Bucket=bucket,
                Prefix=f"{s3_prefix}/processed"
            )
            
            if 'Contents' in response:
                processed_files = [obj for obj in response['Contents'] if not obj['Key'].endswith('/')]
                if len(processed_files) >= num_files:
                    print(f"All {num_files} files have been processed")
                    return True
            
            print(f"Waiting for processing to complete... ({len(processed_files) if 'processed_files' in locals() else 0}/{num_files} files done)")
            time.sleep(10)
            
        except Exception as e:
            print(f"Error checking results: {str(e)}")
            return False
    
    print(f"Timeout waiting for results after {timeout} seconds")
    return False

def verify_results(bucket: str, s3_prefix: str, local_dir: str):
    """Download and verify processed results"""
    s3 = boto3.client('s3')
    output_dir = Path(local_dir) / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        response = s3.list_objects_v2(
            Bucket=bucket,
            Prefix=f"{s3_prefix}/processed"
        )
        
        if 'Contents' not in response:
            print("No processed files found")
            return False
        
        for obj in response['Contents']:
            if obj['Key'].endswith('/'):
                continue
                
            local_file = output_dir / Path(obj['Key']).name
            print(f"Downloading {obj['Key']} to {local_file}")
            s3.download_file(bucket, obj['Key'], str(local_file))
            
            # Verify file content
            with open(local_file, 'r') as f:
                content = f.read()
                if '[Preprocessed at' not in content or '[GPU Processed with' not in content or '[Postprocessed at' not in content:
                    print(f"File {local_file} missing processing markers")
                    return False
        
        print("All files processed successfully with correct markers")
        return True
        
    except Exception as e:
        print(f"Error verifying results: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Test Document AI Pipeline')
    parser.add_argument('--api-url', required=True, help='API Gateway URL')
    parser.add_argument('--bucket', required=True, help='S3 bucket name')
    parser.add_argument('--test-dir', required=True, help='Local directory containing test files')
    parser.add_argument('--s3-prefix', default='test', help='S3 prefix/directory for test files')
    parser.add_argument('--num-files', type=int, default=5, help='Number of test files to create')
    parser.add_argument('--timeout', type=int, default=300, help='Timeout in seconds for processing')
    
    args = parser.parse_args()
    
    print("=== Starting Document AI Pipeline Test ===")
    
    # 1. Create test files
    print("\n1. Creating test files...")
    create_test_files(args.test_dir, args.num_files)
    
    # 2. Upload test files
    print("\n2. Uploading test files to S3...")
    uploaded_count = upload_test_files(args.test_dir, args.bucket, args.s3_prefix)
    
    # 3. Trigger processing
    print("\n3. Triggering document processing...")
    execution_arn = trigger_processing(args.api_url, args.s3_prefix)
    
    # 4. Wait for results
    print("\n4. Waiting for processing to complete...")
    if not wait_for_results(args.bucket, args.s3_prefix, uploaded_count, args.timeout):
        print("Failed: Processing did not complete in time")
        sys.exit(1)
    
    # 5. Verify results
    print("\n5. Verifying processing results...")
    if not verify_results(args.bucket, args.s3_prefix, args.test_dir):
        print("Failed: Result verification failed")
        sys.exit(1)
    
    print("\n=== Document AI Pipeline Test Completed Successfully ===")

if __name__ == '__main__':
    main()
