from db.session import SessionLocal
from services.store_service import StoreService


def main():
    session = SessionLocal()

    try:
        service = StoreService(session)

        print("=" * 60)
        print("All Stores")
        print("=" * 60)

        stores = service.get_all()

        print(f"Count: {len(stores)}")

        for store in stores:
            print(
                f"{store.id} | "
                f"{store.name} | "
                f"Active={store.active}"
            )

        print()

        print("=" * 60)
        print("Active Stores")
        print("=" * 60)

        active = service.get_active()

        print(f"Count: {len(active)}")

        for store in active:
            print(
                f"{store.id} | "
                f"{store.name}"
            )

        print()

        print("=" * 60)
        print("Find mdcomputers")
        print("=" * 60)

        store = service.get_by_name("mdcomputers")

        if store:
            print(store)
        else:
            print("Store not found")

    finally:
        session.close()


if __name__ == "__main__":
    main()