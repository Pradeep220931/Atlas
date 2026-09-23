from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models.entities import KnowledgeArea, KnowledgeGap, Organization, Service, Team, User
from app.security import hash_password

DEMO_USERS = [
    ("Engineering Manager", "manager@finpay.demo", "manager"),
    ("Arun Kumar", "arun@finpay.demo", "holder"),
    ("Priya Sharma", "priya@finpay.demo", "incoming"),
    ("Admin / CTO", "admin@finpay.demo", "admin"),
]
TEAM_NAMES = ["Payments", "Identity", "Orders", "Infrastructure", "Platform"]
SERVICE_NAMES = ["Payment Service", "Refund Engine", "Identity API", "Order Service", "Notification Service"]
GAPS = [
    ("Payment retry policy", "Decision exists, rationale not found", "high"),
    ("Gateway timeout behaviour", "Implementation exists, context unclear", "high"),
    ("Refund reconciliation behaviour", "Operational context unclear", "medium"),
]


def seed_demo_data() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        organization = db.scalar(select(Organization).where(Organization.name == "FinPay / Engineering"))
        if organization is None:
            organization = Organization(name="FinPay / Engineering")
            db.add(organization)
            db.flush()
        teams = {}
        for name in TEAM_NAMES:
            team = db.scalar(select(Team).where(Team.organization_id == organization.id, Team.name == name))
            if team is None:
                team = Team(organization_id=organization.id, name=name)
                db.add(team)
                db.flush()
            teams[name] = team
        for index, (name, email, role) in enumerate(DEMO_USERS):
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                db.add(User(organization_id=organization.id, team_id=teams["Payments"].id, name=name, email=email, role=role, password_hash=hash_password("demo-password")))
        services = {}
        for index, name in enumerate(SERVICE_NAMES):
            if db.scalar(select(Service).where(Service.organization_id == organization.id, Service.name == name)) is None:
                service = Service(organization_id=organization.id, team_id=teams[TEAM_NAMES[index % len(TEAM_NAMES)]].id, name=name, description=f"FinPay {name} service", criticality="high" if index == 0 else "medium")
                db.add(service)
                db.flush()
            else:
                service = db.scalar(select(Service).where(Service.organization_id == organization.id, Service.name == name))
            services[name] = service
        payment_service = services["Payment Service"]
        areas = {}
        for name in ["Payment architecture", "Retry mechanism", "Gateway behaviour", "Refund reconciliation", "Deployment"]:
            area = db.scalar(select(KnowledgeArea).where(KnowledgeArea.service_id == payment_service.id, KnowledgeArea.name == name))
            if area is None:
                area = KnowledgeArea(service_id=payment_service.id, name=name, status="verified" if name in {"Payment architecture", "Retry mechanism", "Deployment"} else "needs_review", criticality="high")
                db.add(area)
                db.flush()
            areas[name] = area
        for index, (title, description, priority) in enumerate(GAPS):
            if db.scalar(select(KnowledgeGap).where(KnowledgeGap.service_id == payment_service.id, KnowledgeGap.title == title)) is None:
                db.add(KnowledgeGap(service_id=payment_service.id, knowledge_area_id=areas[list(areas)[index + 1]].id if index + 1 < len(areas) else areas["Gateway behaviour"].id, title=title, description=description, priority=priority, status="open"))
        db.commit()


if __name__ == "__main__":
    seed_demo_data()
    print("ATLAS demo data seeded")
