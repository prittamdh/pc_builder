from sqlalchemy import text

from db.session import engine


def main():
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version();")).scalar()

            print("✅ Database connection successful!")
            print(version)

    except Exception as e:
        print("❌ Database connection failed!")
        print(e)


if __name__ == "__main__":
    main()