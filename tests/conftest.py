import os
import secrets

os.environ.setdefault("KOBICAM_TEST_MASTER_KEY", secrets.token_bytes(32).hex())
