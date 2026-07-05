import os
from app import create_app

app = create_app(os.getenv("HATA_ENV") or "production")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=app.config.get("DEBUG", False))
