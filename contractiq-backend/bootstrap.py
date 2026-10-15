"""Local Compose bootstrap: migrate and create a private bucket, with bounded startup retry."""
import time

from config import Settings
from migrate import main as migrate
from object_store import ObjectStore


def main() -> None:
    settings = Settings.from_env()
    migrate()
    objects = ObjectStore(settings)
    for attempt in range(20):
        try:
            objects.client.head_bucket(Bucket=settings.s3_bucket)
            break
        except Exception:
            try:
                objects.client.create_bucket(Bucket=settings.s3_bucket)
                break
            except Exception:
                if attempt == 19:
                    raise RuntimeError("Private object bucket could not be initialized") from None
                time.sleep(2)
    print("Private object bucket is ready. No public access policy was added.")


if __name__ == "__main__":
    main()
