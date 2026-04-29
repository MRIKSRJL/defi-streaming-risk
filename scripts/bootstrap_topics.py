import os
from pathlib import Path

import yaml
from confluent_kafka.admin import AdminClient, NewTopic


DEFAULT_TOPICS_PATH = Path("configs/topics.yaml")
DEFAULT_BOOTSTRAP_SERVERS = "localhost:9092"


def load_topic_specs(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    topics = config.get("topics", {})
    if not topics:
        raise ValueError(f"No topics found in config: {path}")
    return topics


def to_new_topic(name: str, spec: dict) -> NewTopic:
    topic_config = {
        "cleanup.policy": spec.get("cleanup_policy", "delete"),
        "retention.ms": str(spec.get("retention_ms", 604800000)),
        "segment.ms": str(spec.get("segment_ms", 3600000)),
        "compression.type": spec.get("compression_type", "zstd"),
    }
    return NewTopic(
        topic=name,
        num_partitions=int(spec.get("partitions", 1)),
        replication_factor=int(spec.get("replication_factor", 1)),
        config=topic_config,
    )


def main() -> None:
    topics_path = Path(os.getenv("TOPICS_CONFIG_PATH", str(DEFAULT_TOPICS_PATH)))
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", DEFAULT_BOOTSTRAP_SERVERS)

    topic_specs = load_topic_specs(topics_path)
    client = AdminClient({"bootstrap.servers": bootstrap_servers})

    existing_topics = client.list_topics(timeout=10).topics
    to_create = [
        to_new_topic(topic_name, topic_specs[topic_name])
        for topic_name in topic_specs
        if topic_name not in existing_topics
    ]

    if not to_create:
        print("No topics to create. All configured topics already exist.")
        return

    futures = client.create_topics(to_create)
    for topic_name, future in futures.items():
        try:
            future.result()
            print(f"Created topic: {topic_name}")
        except Exception as exc:  # pragma: no cover
            print(f"Failed to create topic {topic_name}: {exc}")


if __name__ == "__main__":
    main()
