"""
Google Cloud Pub/Sub setup for Gmail push notifications.

Run this script once to create the topic and subscription.
Requires: pip install google-cloud-pubsub
"""
from google.cloud import pubsub_v1
from google.api_core import exceptions
import os

PROJECT_ID = "zilocrm"
TOPIC_ID = "gmail-notifications"
SUBSCRIPTION_ID = "gmail-notifications-pull"

def create_topic():
    """Create Pub/Sub topic for Gmail notifications."""
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
    
    try:
        topic = publisher.create_topic(request={"name": topic_path})
        print(f"✅ Created topic: {topic.name}")
        return topic
    except exceptions.AlreadyExists:
        print(f"ℹ️  Topic already exists: {topic_path}")
        return publisher.get_topic(request={"topic": topic_path})

def grant_gmail_publish_permission():
    """Grant Gmail API permission to publish to the topic."""
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
    
    policy = publisher.get_iam_policy(request={"resource": topic_path})
    
    gmail_service_account = "gmail-api-push@system.gserviceaccount.com"
    member = f"serviceAccount:{gmail_service_account}"
    
    # Check if permission already exists
    for binding in policy.bindings:
        if binding.role == "roles/pubsub.publisher" and member in binding.members:
            print(f"ℹ️  Permission already granted to {gmail_service_account}")
            return
    
    # Add new binding
    from google.iam.v1 import policy_pb2
    new_binding = policy_pb2.Binding(
        role="roles/pubsub.publisher",
        members=[member]
    )
    policy.bindings.append(new_binding)
    publisher.set_iam_policy(request={"resource": topic_path, "policy": policy})
    print(f"✅ Granted publish permission to {gmail_service_account}")

def create_pull_subscription():
    """Create pull subscription for backend to consume notifications."""
    subscriber = pubsub_v1.SubscriberClient()
    topic_path = subscriber.topic_path(PROJECT_ID, TOPIC_ID)
    subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)
    
    try:
        subscription = subscriber.create_subscription(
            request={
                "name": subscription_path,
                "topic": topic_path,
                "ack_deadline_seconds": 60,
            }
        )
        print(f"✅ Created subscription: {subscription.name}")
        return subscription
    except exceptions.AlreadyExists:
        print(f"ℹ️  Subscription already exists: {subscription_path}")
        return subscriber.get_subscription(request={"subscription": subscription_path})

def main():
    """Run all setup steps."""
    print("🚀 Setting up Google Cloud Pub/Sub for Gmail notifications...\n")
    print(f"Project ID: {PROJECT_ID}")
    print(f"Topic ID: {TOPIC_ID}")
    print(f"Subscription ID: {SUBSCRIPTION_ID}\n")
    
    print("Step 1: Creating topic...")
    create_topic()
    
    print("\nStep 2: Granting Gmail publish permission...")
    grant_gmail_publish_permission()
    
    print("\nStep 3: Creating pull subscription...")
    create_pull_subscription()
    
    print("\n✅ Setup complete!")
    print(f"\nTopic name: projects/{PROJECT_ID}/topics/{TOPIC_ID}")
    print(f"Subscription name: projects/{PROJECT_ID}/subscriptions/{SUBSCRIPTION_ID}")
    print("\nNext steps:")
    print("1. Set GOOGLE_APPLICATION_CREDENTIALS environment variable")
    print("2. Register Gmail watch for each connected user")
    print("3. Start the Pub/Sub listener in your backend")

if __name__ == "__main__":
    main()
