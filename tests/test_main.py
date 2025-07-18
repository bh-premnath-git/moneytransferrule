import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.engine import RuleEngine
from app.models import RuleModel
from fastapi.testclient import TestClient
from app.main import app

def setup_module(_):
    engine = app.state._state["engine"] if hasattr(app.state,"_state") else RuleEngine()
    r = RuleModel(id="R1", enabled=True,
                  routing={"name":"lowIN","match":"amount<5000 and destination_country=='IN'",
                           "methods":["CARD"],"processors":["GW_A","GW_B"],"priority":1,"weight":1})
    engine.load([r]); app.state.engine = engine

client = TestClient(app)

def test_route():
    payload = {"txn_id":"1","destination_country":"IN","amount":4500,"method":"CARD","daily_txn_count":1}
    res = client.post("/evaluate", json=payload)
    assert res.status_code==200 and res.json()["processors"][0]=="GW_A"
