from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.asset import Asset
from app.models.feature_vector import FeatureVector
from app.models.log import Log
from app.models.user import User
from app.services.auth_service import create_user
from app.services.ingestion_service import process_log


def _pick_asset(department: str) -> Asset:
    return Asset.query.filter_by(department=department).first()


def _users_by_role(role: str) -> list[User]:
    return User.query.filter_by(role=role, status="active").all()


def _pick_random_user(role: str) -> User | None:
    users = _users_by_role(role)
    if not users:
        return None
    return random.choice(users)


def _realistic_timestamp_iso(max_age_minutes: int = 120) -> str:
    now = datetime.now(timezone.utc)
    delta_seconds = random.randint(0, max_age_minutes * 60)
    ts = now - timedelta(seconds=delta_seconds)
    return ts.isoformat()


def generate_soc_logs(count: int = 6) -> list[dict]:
    asset = _pick_asset("IT")
    if not asset:
        return []
    attacker_ips = [
        "203.0.113.5",
        "203.0.113.6",
        "198.51.100.23",
        "198.51.100.24",
    ]
    logs = []
    for _ in range(count):
        user = _pick_random_user("soc")
        if not user:
            break

        source_ip = (
            random.choice(attacker_ips)
            if random.random() < 0.6
            else f"192.168.1.{random.randint(2, 250)}"
        )
        attempt_count = random.randint(1, 12)
        success = random.random() < 0.4 if source_ip in attacker_ips else random.random() < 0.85
        event_type = "login_success" if success else "login_failure"
        status = "success" if success else "failed"
        action = "login attempt"

        metadata = {"attempt_count": attempt_count}
        if not success and attempt_count >= 6:
            metadata["attack_type"] = random.choice(["bruteforce", "credential_stuffing"])

        logs.append(
            {
                "timestamp": _realistic_timestamp_iso(),
                "asset_id": asset.id,
                "user_id": user.id,
                "event_type": event_type,
                "action": action,
                "status": status,
                "source_ip": source_ip,
                "destination_ip": "10.0.0.10",
                "metadata": metadata,
            }
        )
    return logs


def generate_finance_logs(count: int = 6) -> list[dict]:
    asset = _pick_asset("Finance")
    if not asset:
        return []
    threshold = 75000.0
    logs = []
    for _ in range(count):
        user = _pick_random_user("finance")
        if not user:
            break
        amount = float(random.randint(100, 100000))
        flagged = amount > threshold
        status = "failed" if flagged and random.random() < 0.35 else "success"
        logs.append(
            {
                "timestamp": _realistic_timestamp_iso(),
                "asset_id": asset.id,
                "user_id": user.id,
                "event_type": "transaction_event",
                "action": random.choice(["transaction processed", "transfer initiated", "withdrawal requested"]),
                "status": status,
                "amount": amount,
                "source_ip": f"172.16.0.{random.randint(2, 250)}",
                "destination_ip": "10.10.10.20",
                "metadata": {
                    "transaction_type": random.choice(["transfer", "withdrawal"]),
                    "flagged": flagged,
                },
            }
        )
    return logs


def generate_hr_logs(count: int = 6) -> list[dict]:
    asset = _pick_asset("HR")
    if not asset:
        return []
    logs = []
    for _ in range(count):
        user = _pick_random_user("hr")
        if not user:
            break

        action_context = random.choice(["view", "modify", "export", "delete"])
        event_type = f"employee_{action_context}"
        action = f"employee record {action_context}"
        off_hours = random.random() < 0.35
        target_user_id = random.randint(10000, 99999)
        data_type = random.choice(["salary", "personal_info", "employment", "benefits"])
        status = random.choice(["success", "denied", "failed"])
        logs.append(
            {
                "timestamp": _realistic_timestamp_iso(),
                "asset_id": asset.id,
                "user_id": user.id,
                "event_type": event_type,
                "action": action,
                "status": status,
                "source_ip": f"10.1.1.{random.randint(2, 250)}",
                "destination_ip": "10.1.2.15",
                "metadata": {
                    "resource": "employee_record",
                    "resource_id": target_user_id,
                    "action_context": action_context,
                    "data_type": data_type,
                    "off_hours": off_hours,
                },
            }
        )
    return logs


def seed_base_data() -> dict:
    seeded_users = [
        ("admin_user", "admin@locknlog.local", "password", "admin", "IT", "full"),
        ("soc_user_1", "soc1@locknlog.local", "password", "soc", "IT", "restricted"),
        ("soc_user_2", "soc2@locknlog.local", "password", "soc", "IT", "restricted"),
        ("fin_user_1", "fin1@locknlog.local", "password", "finance", "Finance", "restricted"),
        ("fin_user_2", "fin2@locknlog.local", "password", "finance", "Finance", "restricted"),
        ("hr_user_1", "hr1@locknlog.local", "password", "hr", "HR", "restricted"),
        ("hr_user_2", "hr2@locknlog.local", "password", "hr", "HR", "restricted"),
        ("observer_user", "observer@locknlog.local", "password", "observer", None, "read-only"),
        ("ceo_user", "ceo@locknlog.local", "password", "ceo", None, "read-only"),
    ]
    for username, email, password, role, department, access_level in seeded_users:
        if not User.query.filter_by(username=username).first():
            create_user(
                username=username,
                email=email,
                password=password,
                role=role,
                department=department,
                access_level=access_level,
                status="active",
            )

    assets = [
        {
            "id": "asset-it-1",
            "name": "web-server",
            "department": "IT",
            "asset_type": "web-server",
            "business_value": 80.0,
            "criticality": 3,
            "sensitivity": "internal",
            "exposure": "internet-facing",
            "ip_address": "10.0.0.10",
            "exposed_ports_json": [80, 443],
        },
        {
            "id": "asset-fin-1",
            "name": "payment-server",
            "department": "Finance",
            "asset_type": "payment-system",
            "business_value": 95.0,
            "criticality": 4,
            "sensitivity": "restricted",
            "exposure": "internal",
            "transaction_volume": 5_500_000.0,
            "avg_transaction_amount": 12_500.0,
        },
        {
            "id": "asset-hr-1",
            "name": "hr-server",
            "department": "HR",
            "asset_type": "hris",
            "business_value": 70.0,
            "criticality": 3,
            "sensitivity": "confidential",
            "exposure": "internal",
            "data_types_json": ["personal_info", "salary"],
            "employee_count": 420,
        },
    ]
    for asset_data in assets:
        if not db.session.get(Asset, asset_data["id"]):
            db.session.add(Asset(**asset_data))

    db.session.commit()

    try:
        FeatureVector.query.delete()
        Log.query.delete()
        db.session.commit()
    except Exception:
        db.session.rollback()

    created_logs = []
    for raw_log in (
        generate_soc_logs(300) + generate_finance_logs(250) + generate_hr_logs(250)
    ):
        created_logs.append(process_log(raw_log).to_dict())

    return {
        "users": User.query.count(),
        "assets": Asset.query.count(),
        "logs_created": len(created_logs),
    }


