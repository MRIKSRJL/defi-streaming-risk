import json
import time
from confluent_kafka import Producer

# --- CONFIGURATION ---
KAFKA_BROKER = 'localhost:9092'
TOPIC = 'aave_raw_events'

# --- L'ÉVÉNEMENT TOXIQUE ---
# On simule un utilisateur qui emprunte une somme colossale d'USDC
# --- L'ÉVÉNEMENT TOXIQUE CORRIGÉ ---
toxic_event = {
    "transaction_hash": "0xDEADBEEF00000000000000000000000000000000000000000000000000000000",
    "block_number": 99999999,
    "timestamp": int(time.time()),
    "event_type": "Borrow",                                  # Corrigé
    "user_address": "0xCRASH_TEST_DUMMY_0000000000000000", # Corrigé
    "reserve_asset": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174", # Corrigé (USDC)
    "amount": 500000000000000000000000  # Emprunt massif
}

def delivery_report(err, msg):
    if err is not None:
        print(f"❌ Échec de l'injection : {err}")
    else:
        print(f"✅ Succès ! Faux événement injecté dans la partition {msg.partition()} du topic {msg.topic()}")

if __name__ == "__main__":
    print("🚀 Préparation de la seringue d'injection Kafka...")
    
    # Création du producteur Kafka minimaliste
    producer = Producer({'bootstrap.servers': KAFKA_BROKER})
    
    # Injection du poison
    producer.produce(
        TOPIC,
        key=toxic_event["user_address"],  # <-- C'est ici qu'il faut remplacer "user" par "user_address"
        value=json.dumps(toxic_event),
        callback=delivery_report
    )
    
    # Attente de la confirmation réseau
    producer.flush()
    print("💉 Le patient a reçu l'injection. Observez l'électrocardiogramme (Terminaux 2 et 3) !")