#!/usr/bin/env python3
import os
import sys
import json
import time
import logging
import torch
from pathlib import Path
from pythonjsonlogger import jsonlogger

# Configure logging
logger = logging.getLogger()
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

def setup_gpu():
    """Setup and verify GPU availability."""
    try:
        if not torch.cuda.is_available():
            logger.error("No GPU available")
            return False
            
        # Set device to GPU
        torch.cuda.set_device(0)
        device_name = torch.cuda.get_device_name(0)
        logger.info(f"Using GPU: {device_name}")
        return True, device_name
    except Exception as e:
        logger.error(f"Error setting up GPU: {str(e)}")
        return False, None

def load_model():
    """
    Load the ML model.
    
    This function loads the ML model from a file and moves it to the GPU.
    It returns True on success and False on failure.
    """
    try:
        # For testing, we'll simulate model loading with a delay
        logger.info("Loading model...")
        time.sleep(1)  # Simulate model loading time
        logger.info("Model loaded successfully")
        return True
    except Exception as e:
        logger.error(f"Error loading model: {str(e)}")
        return False

def process_files(input_dir: str, output_dir: str, device_name: str):
    """Process files using GPU."""
    try:
        # Create output directory if it doesn't exist
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        processed_count = 0
        # Process each file in the input directory
        for file_path in Path(input_dir).glob('*'):
            if file_path.is_file():
                logger.info(f"Processing {file_path}")
                
                # Read input file
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Simulate GPU processing with delay
                time.sleep(2)  # Simulate processing time
                
                # Add GPU processing marker and timestamp
                processed_content = f"{content}\n[GPU Processed with {device_name} at {time.strftime('%Y-%m-%d %H:%M:%S')}]"
                
                # Save processed file
                output_path = Path(output_dir) / file_path.name
                with open(output_path, 'w') as f:
                    f.write(processed_content)
                
                logger.info(f"Saved processed file to {output_path}")
                processed_count += 1
                
        logger.info(f"GPU processed {processed_count} files")
        return True
    except Exception as e:
        logger.error(f"Error in GPU processing: {str(e)}")
        return False

def main():
    try:
        # Setup paths
        efs_mount = '/efs'
        input_dir = os.path.join(efs_mount, 'preprocessed')
        output_dir = os.path.join(efs_mount, 'processed')
        
        # Setup GPU
        gpu_ready, device_name = setup_gpu()
        if not gpu_ready:
            sys.exit(1)
            
        # Load model
        if not load_model():
            sys.exit(1)
            
        # Process files
        if not process_files(input_dir, output_dir, device_name):
            sys.exit(1)
            
        logger.info("GPU processing completed successfully")
        
    except Exception as e:
        logger.error(f"GPU processing failed: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
