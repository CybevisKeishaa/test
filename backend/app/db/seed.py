import asyncio
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
import random

from sqlalchemy import select, insert
from faker import Faker

from app.db.session import async_session_maker
from app.models.user import User
from app.models.todo import Todo
from app.core.security import get_password_hash

DEMO_EMAIL = "demo@test.com"
DEMO_PASSWORD = "Demo@123"
TARGET_USERS = max(1, int(os.getenv("SEED_USERS", "100")))
TARGET_TODOS = max(0, int(os.getenv("SEED_TODOS", "1000")))
USER_BATCH_SIZE = max(1, int(os.getenv("SEED_USER_BATCH_SIZE", "500")))
TODO_BATCH_SIZE = max(1, int(os.getenv("SEED_TODO_BATCH_SIZE", "5000")))


async def seed_db():
    print("Starting database seeding...")
    print(f"Target users: {TARGET_USERS}, target todos: {TARGET_TODOS}")
    start_time = time.time()

    async with async_session_maker() as session:
        # 1. Hashing password once to avoid huge performance penalty
        print("Generating password hash...")
        shared_password_hash = get_password_hash(DEMO_PASSWORD)

        # 2. Check and seed demo user
        result = await session.execute(select(User).where(User.email == DEMO_EMAIL))
        demo_user = result.scalar_one_or_none()

        all_user_ids = []

        if not demo_user:
            print(f"Creating demo user: {DEMO_EMAIL}...")
            demo_user = User(
                id=uuid.uuid4(),
                email=DEMO_EMAIL,
                hashed_password=shared_password_hash,
            )
            session.add(demo_user)
            await session.commit()
            await session.refresh(demo_user)
            print("Demo user created.")
        else:
            print(f"Demo user {DEMO_EMAIL} already exists.")

        all_user_ids.append(demo_user.id)

        # Check if we need to seed the other users
        # Check count of users
        from sqlalchemy import func

        count_result = await session.execute(select(func.count()).select_from(User))
        user_count = count_result.scalar_one()

        if user_count < TARGET_USERS:
            users_to_create = TARGET_USERS - user_count
            print(
                f"Current user count is {user_count}. "
                f"Seeding {users_to_create} more users..."
            )
            fake = Faker()

            # To ensure emails are unique
            existing_emails_result = await session.execute(select(User.email))
            existing_emails = set(existing_emails_result.scalars().all())

            users_batch = []

            for i in range(1, users_to_create + 1):
                email = fake.unique.email()
                while email in existing_emails:
                    email = fake.unique.email()
                existing_emails.add(email)

                user_id = uuid.uuid4()
                all_user_ids.append(user_id)
                users_batch.append(
                    {
                        "id": user_id,
                        "email": email,
                        "hashed_password": shared_password_hash,
                        "created_at": datetime.now(timezone.utc),
                    }
                )

                if len(users_batch) >= USER_BATCH_SIZE or i == users_to_create:
                    await session.execute(insert(User), users_batch)
                    await session.commit()
                    print(f"Inserted {len(users_batch)} users...")
                    users_batch = []
        else:
            print("Users already seeded. Retrieving user IDs...")
            all_users_result = await session.execute(select(User.id))
            all_user_ids = list(all_users_result.scalars().all())

        # 3. Seed TODOs randomly distributed across users
        if TARGET_TODOS == 0:
            print("SEED_TODOS is 0. Skipping TODO seeding.")
            return

        # Check if todos already exist
        result = await session.execute(select(Todo).limit(1))
        has_todos = result.scalar_one_or_none() is not None

        if has_todos:
            print("Database already contains TODOs. Skipping TODO seeding.")
            return

        # Spread created_at over the past two years. Stamping every row with
        # the same `now` makes an index on (user_id, created_at) look useless
        # in a benchmark and hides ordering bugs, because every row ties.
        seed_now = datetime.now(timezone.utc)
        backdate_window_seconds = int(timedelta(days=730).total_seconds())

        print("Pre-generating fake data pools for high performance...")
        fake = Faker()
        titles = [
            fake.sentence(nb_words=random.randint(3, 8)).rstrip(".")
            for _ in range(2000)
        ]
        descriptions = [fake.text(max_nb_chars=150) for _ in range(2000)]

        total_batches = (TARGET_TODOS + TODO_BATCH_SIZE - 1) // TODO_BATCH_SIZE

        print(
            f"Seeding {TARGET_TODOS} TODOs distributed "
            f"across {len(all_user_ids)} users..."
        )

        for batch_offset in range(0, TARGET_TODOS, TODO_BATCH_SIZE):
            batch_started_at = time.time()
            batch_idx = batch_offset // TODO_BATCH_SIZE
            batch_count = min(TODO_BATCH_SIZE, TARGET_TODOS - batch_offset)
            todos_batch = []
            for _ in range(batch_count):
                now = seed_now - timedelta(
                    seconds=random.randint(0, backdate_window_seconds)
                )
                todos_batch.append(
                    {
                        "id": uuid.uuid4(),
                        "title": random.choice(titles),
                        "description": random.choice(descriptions),
                        "completed": random.choice([True, False]),
                        "user_id": random.choice(all_user_ids),
                        "created_at": now,
                        "updated_at": now,
                    }
                )

            # Perform bulk insert
            await session.execute(insert(Todo), todos_batch)
            await session.commit()

            batch_elapsed = time.time() - batch_started_at
            inserted_count = min((batch_idx + 1) * TODO_BATCH_SIZE, TARGET_TODOS)
            print(
                f"Batch {batch_idx + 1}/{total_batches} "
                f"inserted ({inserted_count} total). "
                f"Time: {batch_elapsed:.2f}s"
            )

    end_time = time.time()
    print(f"Database seeding completed in {end_time - start_time:.2f} seconds.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed_db())
