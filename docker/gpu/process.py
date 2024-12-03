#!/usr/bin/env python3
import os
import sys
import json
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
        logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
        return True
    except Exception as e:
        logger.error(f"Error setting up GPU: {str(e)}")
        return False

def load_model():
    """Load the ML model."""
    try:
        # Add your model loading logic here
        # For example:
        # model = torch.load('path_to_model')
        # model.to('cuda')
        return True
    except Exception as e:
        logger.error(f"Error loading model: {str(e)}")
        return False

def process_files(input_dir: str, output_dir: str):
    """Process files using GPU."""
    try:
        # Create output directory if it doesn't exist
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # Process each file in the input directory
        for file_path in Path(input_dir).glob('*'):
            if file_path.is_file():
                logger.info(f"Processing {file_path}")
                
                # Add your GPU processing logic here
                # For example:
                # - Load data
                # - Process with model
                # - Save results
                
                output_path = Path(output_dir) / f"{file_path.stem}_processed{file_path.suffix}"
                # Add your save logic here
                
                logger.info(f"Saved processed file to {output_path}")
                
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
        if not setup_gpu():
            sys.exit(1)
            
        # Load model
        if not load_model():
            sys.exit(1)
            
        # Process files
        if not process_files(input_dir, output_dir):
            sys.exit(1)
            
        logger.info("GPU processing completed successfully")
        
    except Exception as e:
        logger.error(f"GPU processing failed: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
