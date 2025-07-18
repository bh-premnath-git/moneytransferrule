import asyncio
import logging
import json
from typing import Optional
from confluent_kafka import Consumer, KafkaError
from proto_gen import rules_pb2
from models import RuleModel, proto_to_pydantic_rule

logger = logging.getLogger(__name__)

class KafkaConsumerManager:
    def __init__(self, engine, redis, topic="rules"):
        self.engine = engine
        self.redis = redis
        self.topic = topic
        self.consumer: Optional[Consumer] = None
        self.running = False
        
    async def start(self):
        """Start the Kafka consumer with proper error handling"""
        try:
            # Kafka configuration
            conf = {
                "bootstrap.servers": "kafka:9092",
                "group.id": "rule_engine",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": True,
                "session.timeout.ms": 6000,
                "heartbeat.interval.ms": 1000,
                "max.poll.interval.ms": 300000,
                "fetch.wait.max.ms": 500
            }
            
            self.consumer = Consumer(conf)
            self.consumer.subscribe([self.topic])
            self.running = True
            
            logger.info(f"Kafka consumer started for topic: {self.topic}")
            
            # Start polling loop
            await self._poll_loop()
            
        except Exception as e:
            logger.error(f"Failed to start Kafka consumer: {e}")
            raise
    
    async def stop(self):
        """Stop the Kafka consumer gracefully"""
        self.running = False
        if self.consumer:
            self.consumer.close()
            logger.info("Kafka consumer stopped")
    
    async def _poll_loop(self):
        """Main polling loop with error handling"""
        loop = asyncio.get_event_loop()
        
        while self.running:
            try:
                # Poll for messages (non-blocking)
                await loop.run_in_executor(None, self._poll_messages)
                
                # Small delay to prevent busy-waiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in Kafka polling loop: {e}")
                # Continue polling even if individual message processing fails
                await asyncio.sleep(1)
    
    def _poll_messages(self):
        """Poll for messages synchronously"""
        try:
            msg = self.consumer.poll(1.0)
            
            if msg is None:
                return
            
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    logger.debug(f"Reached end of partition: {msg.topic()}")
                else:
                    logger.error(f"Kafka error: {msg.error()}")
                return
            
            # Process the message
            asyncio.create_task(self._process_message(msg.value()))
            
        except Exception as e:
            logger.error(f"Error polling Kafka messages: {e}")
    
    async def _process_message(self, message_bytes: bytes):
        """Process a single Kafka message"""
        try:
            # Parse protobuf message
            proto_rule = rules_pb2.Rule()
            proto_rule.ParseFromString(message_bytes)
            
            # Convert to Pydantic model
            pydantic_rule = proto_to_pydantic_rule(proto_rule)
            
            # Validate the rule
            if not pydantic_rule.id:
                logger.warning("Received rule without ID, skipping")
                return
            
            # Store in Redis
            rule_key = f"rule:{pydantic_rule.id}"
            await self.redis.set(rule_key, message_bytes)
            
            # Update engine with new rule
            current_rules = [r for r in self.engine.rules if r.id != pydantic_rule.id]
            current_rules.append(pydantic_rule)
            self.engine.load(current_rules)
            
            logger.info(f"Processed rule update: {pydantic_rule.id}")
            
        except Exception as e:
            logger.error(f"Failed to process Kafka message: {e}")
            # Don't re-raise - continue processing other messages

# Global consumer manager instance
consumer_manager: Optional[KafkaConsumerManager] = None

async def start(engine, redis, topic="rules"):
    """Start the Kafka consumer (backwards compatibility)"""
    global consumer_manager
    
    try:
        consumer_manager = KafkaConsumerManager(engine, redis, topic)
        await consumer_manager.start()
        
    except Exception as e:
        logger.error(f"Failed to start Kafka consumer: {e}")
        raise

async def stop():
    """Stop the Kafka consumer"""
    global consumer_manager
    
    if consumer_manager:
        await consumer_manager.stop()
        consumer_manager = None
