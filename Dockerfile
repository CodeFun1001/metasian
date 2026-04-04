FROM python:3.10-slim

WORKDIR /app

# Copy your files into the container
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# OpenEnv needs port 7860 for Hugging Face
EXPOSE 7860

# Start the environment
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]