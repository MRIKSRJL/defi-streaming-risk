import asyncio
import logging
import os
import signal
import sys

from pydantic import ValidationError

from schemas.feature_vectors import RiskFeatureVector
from src.infra.kafka.consumer import AsyncKafkaConsumer
from src.infra.kafka.producer import AsyncKafkaProducer
from src.ml.predictor import RiskPredictor


logger = logging.getLogger(__name__)


class InferenceRunner:
    def __init__(
        self,
        *,
        kafka_bootstrap_servers: str,
        features_topic: str,
        alerts_topic: str,
        group_id: str,
    ) -> None:
        self._consumer = AsyncKafkaConsumer(
            {
                "bootstrap.servers": kafka_bootstrap_servers,
                "group.id": group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": True,
            }
        )
        self._producer = AsyncKafkaProducer(
            {
                "bootstrap.servers": kafka_bootstrap_servers,
                "client.id": "aave-inference-producer-v1",
            }
        )
        self._predictor = RiskPredictor()
        self._features_topic = features_topic
        self._alerts_topic = alerts_topic
        self._shutdown_event = asyncio.Event()
        self._shutdown_started = False

    async def run(self) -> None:
        await self._producer.start()
        self._consumer.subscribe([self._features_topic])
        logger.info("Inference runner started topic=%s -> alerts=%s", self._features_topic, self._alerts_topic)

        try:
            async for msg in self._consumer.messages():
                if self._shutdown_event.is_set():
                    break
                await self._process_message(msg.value())
        except asyncio.CancelledError:
            logger.info("Inference runner cancelled.")
            raise
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._shutdown_event.set()
        await self._consumer.close()
        await self._producer.close(flush_timeout_seconds=2.0)
        logger.info("Inference runner stopped cleanly.")

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    async def _process_message(self, value: bytes | str | None) -> None:
        if value is None:
            return
        payload = value.decode("utf-8") if isinstance(value, bytes) else value

        try:
            feature_vector = RiskFeatureVector.model_validate_json(payload)
        except ValidationError:
            logger.exception("Skipping invalid RiskFeatureVector payload.")
            return

        alert = self._predictor.predict(feature_vector)
        
        if alert.risk_level in {"HIGH", "CRITICAL"}:
            await self._producer.produce(
                topic=self._alerts_topic,
                key=alert.user_address,
                value=alert.model_dump_json(),
            )
            logger.warning(
                "LIQUIDATION ALERT user=%s risk=%s probability=%.2f",
                alert.user_address,
                alert.risk_level,
                alert.predicted_probability,
            )
        else:
            logger.info(f"Dossier analysé : user={alert.user_address[:8]}... | Risque: {alert.risk_level} | Probabilité: {alert.predicted_probability:.4f}")


def _register_signal_handlers(runner: InferenceRunner, run_task: asyncio.Task[None]) -> None:
    signal_seen = False

    def _handler(signum, frame) -> None:  # type: ignore[no-untyped-def,unused-argument]
        nonlocal signal_seen
        if signal_seen:
            return
        signal_seen = True
        logger.info("Received signal %s, requesting shutdown.", signum)
        runner.request_shutdown()
        run_task.cancel()

    signal.signal(signal.SIGINT, _handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handler)


async def main() -> None:
    runner = InferenceRunner(
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        features_topic=os.getenv("FEATURES_TOPIC", "defi_features"),
        alerts_topic=os.getenv("LIQUIDATION_ALERTS_TOPIC", "liquidation_alerts"),
        group_id=os.getenv("INFERENCE_CONSUMER_GROUP_ID", "aave-inference-v1"),
    )

    run_task = asyncio.create_task(runner.run())
    _register_signal_handlers(runner, run_task)

    try:
        await run_task
    except asyncio.CancelledError:
        logger.info("Main inference task cancelled.")
    finally:
        try:
            await asyncio.wait_for(runner.shutdown(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("Inference shutdown exceeded 5s, forcing exit.")
            sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
