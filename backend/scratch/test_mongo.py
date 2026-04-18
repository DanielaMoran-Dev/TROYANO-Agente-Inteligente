
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import certifi
import socket

async def test_mongo_connection():
    load_dotenv("/home/angel/Escritorio/TROYANO-Agente-Inteligente/backend/services/.env")
    uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB_NAME", "healthapp")

    print(f"Testing connection to: {uri.split('@')[-1] if uri else 'None'}")
    
    # Check DNS resolution for the cluster
    try:
        cluster_host = uri.split('@')[-1].split('/')[0]
        print(f"Attempting to resolve host: {cluster_host}")
        # Note: SRV records are harder to resolve with socket.gethostbyname, 
        # but let's see if the base domain resolves or at least we can reach google.
        socket.gethostbyname("google.com")
        print("Basic internet connectivity (google.com) confirmed.")
    except Exception as e:
        print(f"DNS/Internet check failed: {e}")

    client = AsyncIOMotorClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
    
    try:
        # The 'ping' command is cheap and does not require auth for some clusters, 
        # but verifies the server is reachable.
        await client.admin.command('ping')
        print("✅ Successfully connected to MongoDB Atlas!")
        
        # Try to list collections in the specific DB to verify auth
        db = client[db_name]
        collections = await db.list_collection_names()
        print(f"✅ Successfully authenticated! Collections in {db_name}: {collections}")
        
    except Exception as e:
        print(f"❌ Failed to connect to MongoDB: {type(e).__name__}: {e}")
        print("\nCommon fixes:")
        print("1. IP Whitelisting: Go to MongoDB Atlas -> Network Access and add your current IP.")
        print("2. URI format: Ensure the username and password are correct and URL-encoded if they contain special characters.")
        print("3. Port 27017: Ensure your firewall/ISP allows traffic on port 27017.")

if __name__ == "__main__":
    asyncio.run(test_mongo_connection())
