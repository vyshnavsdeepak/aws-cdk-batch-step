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

def upload_to_s3(s3_client, local_dir: str, bucket: str, output_dir: str):
    """Upload processed files to S3."""
    try:
        # Upload each file in the directory
        for file_path in Path(local_dir).glob('*'):
            if file_path.is_file():
                s3_key = f"{output_dir}/{file_path.name}"
                logger.info(f"Uploading {file_path} to s3://{bucket}/{s3_key}")
                
                s3_client.upload_file(
                    str(file_path),
                    bucket,
                    s3_key
                )
                
        return True
    except Exception as e:
        logger.error(f"Error uploading to S3: {str(e)}")
        return False

def postprocess_files(input_dir: str, output_dir: str):
    """Post-process files and prepare for upload."""
    try:
        # Create output directory if it doesn't exist
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        processed_count = 0
        # Process each file in the input directory
        for file_path in Path(input_dir).glob('*'):
            if file_path.is_file():
                logger.info(f"Post-processing {file_path}")
                
                # Read the input file
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Add postprocessing marker and timestamp
                final_content = f"{content}\n[Postprocessed at {time.strftime('%Y-%m-%d %H:%M:%S')}]"
                
                # Save processed file
                output_path = Path(output_dir) / file_path.name
                with open(output_path, 'w') as f:
                    f.write(final_content)
                
                logger.info(f"Saved post-processed file to {output_path}")
                processed_count += 1
                
        logger.info(f"Post-processed {processed_count} files")
        return True
    except Exception as e:
        logger.error(f"Error in post-processing: {str(e)}")
        return False

def main():
    try:
        # Get environment variables
        output_bucket = os.environ.get('OUTPUT_BUCKET')
        output_prefix = os.environ.get('OUTPUT_PREFIX')
        
        if not all([output_bucket, output_prefix]):
            logger.error("Required environment variables are missing")
            sys.exit(1)
            
        # Setup paths
        efs_mount = '/efs'
        input_dir = os.path.join(efs_mount, 'processed')
        local_output = '/tmp/output'
        
        # Initialize AWS clients
        s3_client = setup_aws_clients()
        
        # Post-process files
        if not postprocess_files(input_dir, local_output):
            sys.exit(1)
            
        # Upload to S3
        if not upload_to_s3(s3_client, local_output, output_bucket, output_prefix):
            sys.exit(1)
            
        logger.info("Post-processing completed successfully")
        
    except Exception as e:
        logger.error(f"Post-processing failed: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
