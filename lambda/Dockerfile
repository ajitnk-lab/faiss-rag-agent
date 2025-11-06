FROM public.ecr.aws/lambda/python:3.12

# Install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir faiss-cpu numpy boto3 -t ${LAMBDA_TASK_ROOT}/

# Copy function code
COPY query_handler.py ${LAMBDA_TASK_ROOT}/

# Set handler
CMD ["query_handler.lambda_handler"]
