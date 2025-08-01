FROM python:3.8-slim

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Optional: for non-root user security
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /usr/src/app
USER appuser

EXPOSE 8000

ENV SCRAPER_URL=https://www.1tamilmv.se/
ENV REFRESH_INTERVAL=60

CMD ["python", "scraper.py"]
