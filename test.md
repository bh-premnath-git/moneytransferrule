# Test REST API - Windows PowerShell Commands

## Health Check
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
```

## Rule Evaluation Test
```powershell
$body = @{
    txn_id = "test-123"
    amount = 1000
    currency = "USD"
    source_country = "US"
    destination_country = "CA"
    method = "CARD"
    daily_txn_count = 1
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/evaluate" -Method Post -Body $body -ContentType "application/json"
```

## Metrics
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/metrics" -Method Get
```

## Alternative: Using curl.exe directly
```cmd
curl.exe http://localhost:8000/health
curl.exe -X POST http://localhost:8000/evaluate -H "Content-Type: application/json" -d "{\"transaction_id\":\"test-123\",\"amount\":1000,\"currency\":\"USD\",\"from_country\":\"US\",\"to_country\":\"CA\",\"method\":\"CARD\"}"
curl.exe http://localhost:8000/metrics
```

## Create Kafka Topic (Optional)
```powershell
docker exec money-transfer-kafka kafka-topics --create --topic rules --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
```

## Metrics
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/metrics" -Method Get
```

## Alternative: Using curl.exe directly
```cmd
curl.exe http://localhost:8000/health
curl.exe -X POST http://localhost:8000/evaluate -H "Content-Type: application/json" -d "{\"transaction_id\":\"test-123\",\"amount\":1000,\"currency\":\"USD\",\"from_country\":\"US\",\"to_country\":\"CA\",\"method\":\"CARD\"}"
curl.exe http://localhost:8000/metrics
```

## Create Kafka Topic (Optional)
```powershell
docker exec money-transfer-kafka kafka-topics --create --topic rules --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1