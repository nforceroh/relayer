from app.config import load
from app.main import create_app
from app.store import store_from_env

settings = load()
app = create_app(settings, store_from_env(settings))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
