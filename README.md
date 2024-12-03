# Document AI Pipeline

A scalable, serverless document processing pipeline built with AWS CDK. This pipeline processes documents using a combination of CPU and GPU instances, with automatic scaling and fault tolerance.

## Architecture

### Infrastructure Components
- **S3 Bucket**: Persistent storage in us-east-1 region
- **EC2 Instances**:
  - t3.medium instances for preprocessing and postprocessing
  - g6e.xlarge12 GPU instance for main processing
  - All instances run as spot instances with automatic retry logic
- **EFS**: Shared storage between processing steps
- **Step Functions**: Workflow orchestration
- **AWS Batch**: Job scheduling and compute management
- **API Gateway**: RESTful API endpoint for triggering the pipeline

### Processing Flow
1. Files are uploaded to S3 under a specific directory
2. API is called with the directory name
3. Preprocessing job runs on CPU instance
4. Main processing job runs on GPU instance
5. Postprocessing job runs on CPU instance
6. Results are stored back in S3

## Prerequisites

- Node.js (v14 or later)
- AWS CLI configured with appropriate credentials
- Docker installed locally
- AWS CDK CLI (`npm install -g aws-cdk`)

## Project Structure

```
.
├── bin/
│   └── doc-ai-pipeline.ts    # CDK app entry point
├── lib/
│   └── doc-ai-pipeline-stack.ts    # Main stack definition
├── docker/
│   ├── preprocess/           # CPU preprocessing container
│   ├── gpu/                  # GPU processing container
│   └── postprocess/          # CPU postprocessing container
└── cdk.json                  # CDK configuration
```

## Deployment

1. Install dependencies:
```bash
npm install
```

2. Build the TypeScript code:
```bash
npm run build
```

3. Bootstrap CDK (one-time setup):
```bash
npx cdk bootstrap
```

4. Deploy the stack:
```bash
npx cdk deploy
```

### Deployment Notes
- Deployment time: ~15-20 minutes
- S3 bucket persists even after stack deletion
- Docker images are automatically built and pushed to ECR
- Security prompts will appear for IAM changes

## Usage

1. Get the deployment outputs:
   - API Gateway endpoint URL
   - Source S3 bucket name

2. Upload files:
```bash
aws s3 cp ./your-files s3://your-bucket-name/your-directory/
```

3. Trigger processing:
```bash
curl -X POST https://your-api-endpoint/prod/process \
  -H "Content-Type: application/json" \
  -d '{"directory": "your-directory"}'
```

## Monitoring

- **CloudWatch Logs**: Contains logs from all processing steps
- **Step Functions Console**: Visual workflow monitoring
- **AWS Batch Console**: Job execution status and details

## Security Features

- Private VPC configuration
- IAM roles with least privilege
- S3 bucket encryption
- API Gateway authentication ready
- EFS access control

## Cost Optimization

- Uses spot instances for cost savings
- Automatic scaling based on workload
- Intelligent storage tiering
- Resource cleanup after processing

## Troubleshooting

Common issues:
1. **Deployment Failures**: Check CloudFormation console for detailed error messages
2. **Job Failures**: Check CloudWatch Logs for specific job logs
3. **Spot Instance Interruptions**: Jobs automatically retry on new instances

## Development Commands

* `npm run build`   compile typescript to js
* `npm run watch`   watch for changes and compile
* `npm run test`    perform the jest unit tests
* `npx cdk deploy`  deploy this stack to your default AWS account/region
* `npx cdk diff`    compare deployed stack with current state
* `npx cdk synth`   emits the synthesized CloudFormation template

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
