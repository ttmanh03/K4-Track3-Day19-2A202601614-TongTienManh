import os, socket, sys
from dotenv import load_dotenv
load_dotenv()

uri = os.environ.get("NEO4J_URI", "")
user = os.environ.get("NEO4J_USER", "neo4j")
pwd = os.environ.get("NEO4J_PASSWORD", "")
host = uri.split("://", 1)[-1].split("/")[0].split(":")[0]

print("URI scheme:", uri.split("://")[0], "| host:", host)

try:
    print("DNS ->", socket.gethostbyname(host))
except Exception as e:
    print("DNS FAILED:", type(e).__name__, e)

for port in (7687, 443):
    s = socket.socket()
    s.settimeout(8)
    try:
        s.connect((host, port))
        print(f"TCP {port}: OPEN")
    except Exception as e:
        print(f"TCP {port}: FAILED {type(e).__name__} {e}")
    finally:
        s.close()

import neo4j
from neo4j import GraphDatabase
print("neo4j driver:", neo4j.__version__)

for scheme in ("neo4j+s", "bolt+s", "neo4j+ssc", "bolt+ssc"):
    test_uri = f"{scheme}://{host}"
    try:
        d = GraphDatabase.driver(test_uri, auth=(user, pwd), connection_timeout=15)
        d.verify_connectivity()
        with d.session(database=os.environ.get("NEO4J_DATABASE", "neo4j")) as ses:
            n = ses.run("RETURN 1 AS ok").single()["ok"]
        print(f"{scheme}: OK (query returned {n})")
        d.close()
    except Exception as e:
        print(f"{scheme}: FAILED {type(e).__name__}: {str(e)[:200]}")
