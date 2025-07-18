# Test REST API health
curl http://localhost:8000/health

# Test rule evaluation
curl -X POST http://localhost:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "test-123",
    "amount": 1000,
    "currency": "USD",
    "from_country": "US",
    "to_country": "CA",
    "method": "CARD"
  }'

# Test metrics
curl http://localhost:8000/metrics

# Optional: Create Kafka topic for full integration
docker exec money-transfer-kafka kafka-topics --create --topic rules --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1