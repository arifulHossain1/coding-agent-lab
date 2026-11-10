FROM python:3.11-slim

RUN pip install --no-cache-dir pytest && useradd --create-home runner
ENV PYTHONDONTWRITEBYTECODE=1
USER runner
WORKDIR /workspace
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
