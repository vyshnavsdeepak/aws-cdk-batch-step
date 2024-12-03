#!/usr/bin/env python3
import os
import sys
import json
import logging
import boto3
from pathlib import Path
from pythonjsonlogger import jsonlogger
import time

# Configure logging
logger = logging.getLogger()
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

def setup_aws_clients():
    """Initialize AWS clients with proper error handling."""
    try:
        s3 = boto3.client('s3')
        return s3
    except Exception as e:
        logger.error(f"Failed to initialize AWS clients: {str(e)}")
        sys.exit(1)

def download_from_s3(s3_client, bucket: str, directory: str, local_dir: str):
    """Download files from S3 directory to local directory."""
    try:
        # List objects in the S3 directory
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=directory
        )
        
        if 'Contents' not in response:
            logger.error(f"No files found in s3://{bucket}/{directory}")
            return False

        # Create local directory if it doesn't exist
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        
        # Download each file
        for obj in response['Contents']:
            if obj['Key'].endswith('/'):  # Skip directories
                continue
                
            local_file = os.path.join(local_dir, os.path.basename(obj['Key']))
            logger.info(f"Downloading {obj['Key']} to {local_file}")
            s3_client.download_file(bucket, obj['Key'], local_file)
            
        return True
    except Exception as e:
        logger.error(f"Error downloading from S3: {str(e)}")
        return False

def preprocess_files(input_dir: str, output_dir: str):
    """Preprocess files in the input directory and save to output directory."""
    try:
        # Create output directory if it doesn't exist
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        processed_count = 0
        # Process each file in the input directory
        for file_path in Path(input_dir).glob('*'):
            if file_path.is_file():
                logger.info(f"Processing {file_path}")
                
                # Read the input file
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Add preprocessing marker and timestamp
                processed_content = f"[Preprocessed at {time.strftime('%Y-%m-%d %H:%M:%S')}]\n{content}"
                
                # Save processed file
                output_path = Path(output_dir) / file_path.name
                with open(output_path, 'w') as f:
                    f.write(processed_content)
                
                logger.info(f"Saved preprocessed file to {output_path}")
                processed_count += 1
                
        logger.info(f"Preprocessed {processed_count} files")
        return True
    except Exception as e:
        logger.error(f"Error in preprocessing: {str(e)}")
        return False

def main():
    try:
        # Get environment variables
        source_bucket = os.environ.get('SOURCE_BUCKET')
        input_dir = os.environ.get('INPUT_DIRECTORY')
        
        if not all([source_bucket, input_dir]):
            logger.error("Required environment variables are missing")
            sys.exit(1)
            
        # Setup paths
        efs_mount = '/efs'
        local_input = '/tmp/input'
        local_output = os.path.join(efs_mount, 'preprocessed')
        
        # Initialize AWS clients
        s3_client = setup_aws_clients()
        
        # Download files from S3
        if not download_from_s3(s3_client, source_bucket, input_dir, local_input):
            sys.exit(1)
            
        # Preprocess files
        if not preprocess_files(local_input, local_output):
            sys.exit(1)
            
        logger.info("Preprocessing completed successfully")
        
    except Exception as e:
        logger.error(f"Preprocessing failed: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
