#!/usr/bin/env python3
import os
import sys
import json
import time
import boto3
import requests
import argparse
import pytest
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from botocore.exceptions import ClientError

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

class TestDocAIPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = "test_files"
        cls.bucket = "test-doc-ai-bucket"
        cls.s3_prefix = "test-docs"
        cls.api_url = "http://test-api-endpoint/process"
        
        # Create test directory if it doesn't exist
        Path(cls.test_dir).mkdir(parents=True, exist_ok=True)

    def setUp(self):
        """Set up test fixtures before each test method"""
        self.s3_client = boto3.client('s3')
        
    def tearDown(self):
        """Clean up after each test"""
        # Clean up test files
        for file_path in Path(self.test_dir).glob('*'):
            if file_path.is_file():
                file_path.unlink()

    def test_create_test_files(self):
        """Test creation of sample test files"""
        num_files = 3
        create_test_files(self.test_dir, num_files)
        
        files = list(Path(self.test_dir).glob('*'))
        self.assertEqual(len(files), num_files)
        for file in files:
            self.assertTrue(file.is_file())
            self.assertTrue(file.stat().st_size > 0)

    @patch('boto3.client')
    def test_upload_test_files(self, mock_boto3_client):
        """Test uploading files to S3"""
        # Create some test files
        create_test_files(self.test_dir, 2)
        
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto3_client.return_value = mock_s3
        
        # Test upload
        upload_test_files(self.test_dir, self.bucket, self.s3_prefix)
        
        # Verify S3 upload was called for each file
        self.assertEqual(mock_s3.upload_file.call_count, 2)

    @patch('requests.post')
    def test_trigger_processing(self, mock_post):
        """Test triggering the processing pipeline"""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "processing", "job_id": "test-job-123"}
        
        response = trigger_processing(self.api_url, self.test_dir)
        self.assertEqual(response["status"], "processing")
        self.assertEqual(response["job_id"], "test-job-123")

    @patch('boto3.client')
    def test_wait_for_results(self, mock_boto3_client):
        """Test waiting for processing results"""
        # Mock S3 client list_objects response
        mock_s3 = Mock()
        mock_s3.list_objects_v2.return_value = {
            'Contents': [{'Key': f"{self.s3_prefix}/result_1.json"}]
        }
        mock_boto3_client.return_value = mock_s3
        
        # Test with shorter timeout for testing
        result = wait_for_results(self.bucket, self.s3_prefix, 1, timeout=5)
        self.assertTrue(result)

    @patch('boto3.client')
    def test_verify_results(self, mock_boto3_client):
        """Test verification of processed results"""
        # Mock S3 client get_object response
        mock_s3 = Mock()
        mock_s3.get_object.return_value = {
            'Body': Mock(read=lambda: json.dumps({
                'document_id': 'test_doc_1',
                'status': 'completed',
                'results': {'text': 'Sample processed text'}
            }).encode())
        }
        mock_boto3_client.return_value = mock_s3
        
        # Create output directory
        output_dir = Path(self.test_dir) / "results"
        output_dir.mkdir(exist_ok=True)
        
        # Test verification
        results = verify_results(self.bucket, self.s3_prefix, str(output_dir))
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]['status'], 'completed')

    def test_error_handling(self):
        """Test error handling scenarios"""
        # Test with invalid directory
        with self.assertRaises(FileNotFoundError):
            trigger_processing(self.api_url, "invalid_directory")
        
        # Test with invalid bucket
        with patch('boto3.client') as mock_boto3_client:
            mock_s3 = Mock()
            mock_s3.upload_file.side_effect = ClientError(
                {'Error': {'Code': 'NoSuchBucket', 'Message': 'The bucket does not exist'}},
                'upload_file'
            )
            mock_boto3_client.return_value = mock_s3
            
            with self.assertRaises(ClientError):
                upload_test_files(self.test_dir, "invalid-bucket", self.s3_prefix)

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
    unittest.main(exit=False)
    main()
