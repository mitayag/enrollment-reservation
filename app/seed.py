"""Idempotent data seeding. Run with: python -m app.seed"""

from app.database import SessionLocal
from app.services import program_service


def main() -> None:
    with SessionLocal() as db:
        created = program_service.seed_programs(db)
        if created:
            print(f"Seeded {len(created)} program(s): {', '.join(p.code for p in created)}")
        else:
            print("Programs already seeded; nothing to do.")


if __name__ == "__main__":
    main()
